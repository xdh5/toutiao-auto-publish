#!/usr/bin/env python3
"""NBA 媒体数据采集 — 直播吧赛程、战报与新闻。

使用 requests + BeautifulSoup 采集体育媒体数据。
- 主源：直播吧篮球频道 — NBA赛程、比分、战报与新闻

数据由专业记者核实，改写时确保事实准确。

用法:
    from media_scraper import SportsScraper
    scraper = SportsScraper()
    matches = scraper.scrape_today_matches("2026-06-30")
    report = scraper.scrape_match_report("https://...matchXXX.htm")
    news = scraper.scrape_hot_news()

输出格式:
    match = {
        "source": "zhibo8",
        "match_url": "https://...",
        "home_team": "湖人", "away_team": "勇士",
        "home_score": 118, "away_score": 112,
        "status": "FT",  # FT/LIVE/PRE
        "league": "NBA",
        "match_date": "2026-06-30",
    }

    report = {
        "source": "zhibo8",
        "match_url": "https://...",
        "article_title": "巴西2-1绝杀日本",
        "article_text": "完整战报正文（记者已核实）",
        "home_team": "巴西", "away_team": "日本",
        "home_score": 2, "away_score": 1,
        "goals": [{"minute": 95, "scorer": "马丁内利", "scorer_team": "home"}],
        "data_confidence": "high",
    }
"""

import re, json, time, random, sys
from datetime import datetime, timedelta
from typing import Optional
import requests
from bs4 import BeautifulSoup


class ScraperBlockedError(Exception):
    """Raised when the source blocks our requests."""
    pass


class ScraperParseError(Exception):
    """Raised when response HTML can't be parsed."""
    pass


class SportsScraper:
    """体育媒体数据采集器（直播吧 + 懂球帝）

    爬取策略：
    1. 直播吧 — 赛程页取比赛列表，战报页取全文（优先）
    2. 懂球帝 — 直接访问文章详情页（备源）
    3. 都不可用 → ScraperBlockedError → 调用方降级
    """

    # ==================== 直播吧 ====================
    ZHIBO8_BASE = "https://www.zhibo8.com"
    ZHIBO8_NEWS = "https://news.zhibo8.com"

    # 赛程页选择器 (支持降级链，选第一个有效的)
    ZHIBO8_SCHEDULE_SELS = [".schedule", ".match-list", "#schedule",
                             "[class*='schedule']", "[id*='schedule']"]
    ZHIBO8_FOOTBALL_ITEM_SELS = ["li[data-type='basketball']",
                                   "li[class*='basketball']",
                                   "[class*='match-item']",
                                   "[class*='game-item']"]
    ZHIBO8_TEAMS_SELS = ["._teams", "[class*='teams']", "[class*='team-name']",
                          "[class*='team_name']"]
    ZHIBO8_LEAGUE_SELS = ["._league", "[class*='league']", "[class*='league-name']"]
    ZHIBO8_CONTENT_SELS = [".content", ".article-content", ".detail",
                            ".news-content", "#content", "article"]
    ZHIBO8_NEWS_LINK_SELS = [r"nba/\d{4}-\d{2}-\d{2}/\w+native\.htm",
                               r"nba/\d{4}-\d{2}-\d{2}/\w+\.htm",
                               r"news.*match"]

    # ==================== 懂球帝 ====================
    DQ_BASE = "https://www.dongqiudi.com"
    DQ_ARTICLE_SELS = [".detail", ".article-content", ".content",
                        ".news-content", "article", ".rich-content"]

    # ==================== 反爬配置 ====================
    REQUEST_DELAY = 1.0
    MAX_RETRIES = 3
    TIMEOUT = 15
    BACKOFF_BASE = 2

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148",
    ]

    _consecutive_blocks = 0
    _last_request_time = 0
    BLOCK_THRESHOLD = 3

    # NBA 相关赛事名统一成 NBA；其余篮球赛事在入口过滤。
    LEAGUE_MAP = {
        "NBA": "NBA", "季前赛": "NBA", "常规赛": "NBA",
        "附加赛": "NBA", "季后赛": "NBA", "总决赛": "NBA",
    }

    def __init__(self):
        self.session = requests.Session()
        self._rotate_ua()

    # ------------------------------------------------------------------
    #  Selector 降级工具 — 当网站HTML改版时自动尝试备用选择器
    # ------------------------------------------------------------------

    @staticmethod
    def _select_one_fallback(soup, selectors, default=None):
        """遍历选择器列表，返回第一个匹配的元素。

        当网站改版、CSS类名变化时，降级链可自动适配。
        """
        if not selectors:
            return default
        if isinstance(selectors, str):
            return soup.select_one(selectors) or default
        for sel in selectors:
            el = soup.select_one(sel)
            if el is not None:
                return el
        return default

    @staticmethod
    def _find_all_fallback(soup, selectors, default=None):
        """遍历选择器列表，返回第一个非空的结果集。"""
        if not selectors:
            return default or []
        if isinstance(selectors, str):
            return soup.select(selectors) or default or []
        for sel in selectors:
            results = soup.select(sel)
            if results:
                return results
        return default or []

    @staticmethod
    def _find_all_fallback_regex(soup, patterns, attr="href"):
        """遍历所有正则模式，合并去重返回全部匹配元素。

        注意：与 _select_one_fallback / _find_all_fallback 不同，
        此方法会尝试所有模式并合并结果（而非第一个有结果就返回），
        因为不同模式匹配不同类型的链接，需要全部收集。
        """
        if isinstance(patterns, str):
            patterns = [patterns]
        seen = set()
        all_results = []
        for pat in patterns:
            results = soup.find_all("a", href=re.compile(pat, re.I))
            for r in results:
                key = r.get("href", "")
                if key and key not in seen:
                    seen.add(key)
                    all_results.append(r)
        return all_results

    def _auto_detect_selectors(self, soup):
        """当所有降级链失效时，尝试自动发现新的选择器。

        通过寻找"中文队名+数字比分"文本模式来推断容器。
        适用于网站完全重构后，CSS类名全部变更的场景。

        返回 dict: {"schedule_sel": str, "football_sel": str,
                     "teams_sel": str, "league_sel": str}
                元素为空表示未找到
        """
        result = {"schedule_sel": "", "football_sel": "",
                  "teams_sel": "", "league_sel": ""}

        # 尝试找到包含比分模式(中文+数字+横线+数字)的容器
        score_pattern = re.compile(r"([一-鿿]{2,6})\s*\d+\s*[-–:]\s*\d+\s*([一-鿿]{2,6})")
        candidates = []

        for el in soup.find_all(["li", "div", "tr"]):
            text = el.get_text(strip=True)
            if score_pattern.search(text):
                # 检查是否包含链接
                if el.find("a", href=re.compile(r"match", re.I)):
                    candidates.append(el)
                    if len(candidates) >= 3:
                        break

        if candidates:
            # 用第一个候选元素推断选择器
            first = candidates[0]
            # 找共同父容器
            parent = first.parent
            if parent and parent.name in ("div", "ul", "tbody"):
                class_names = " ".join(parent.get("class", []))
                if class_names:
                    result["schedule_sel"] = f"{parent.name}.{class_names.replace(' ', '.')}"

            # 推断足球条目选择器
            tag = first.name
            cls = " ".join(first.get("class", []))
            if cls:
                result["football_sel"] = f"{tag}.{cls.replace(' ', '.')}"

            # 推断队名选择器: 找比分前后的中文元素
            teams_el = first.find("span", string=re.compile(r"[一-鿿]{2,6}"))
            if teams_el:
                cls = " ".join(teams_el.get("class", []))
                if cls:
                    result["teams_sel"] = f"span.{cls.replace(' ', '.')}"

        return result

    # ------------------------------------------------------------------
    #  公开接口
    # ------------------------------------------------------------------

    def scrape_today_matches(self, date_str: str = None) -> list[dict]:
        """获取今日比赛列表（从直播吧首页解析）。

        返回比赛 dict 列表，含双方队名、比分（如有）、联赛名、战报链接。
        当天无比赛或无法获取时返回 []。
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        try:
            html = self._http_get(f"{self.ZHIBO8_BASE}/")
            matches = self._parse_zhibo8_homepage(html, date_str)
            self._consecutive_blocks = 0
            # 空列表是NBA休赛期/无比赛日的正常结果，不能再从全站新闻标题反推。
            return matches
        except ScraperBlockedError:
            self._consecutive_blocks += 1
            if self._consecutive_blocks >= self.BLOCK_THRESHOLD:
                raise
        except Exception as e:
            print(f"   ⚠️ 直播吧首页解析异常: {e}")

        return []

    def scrape_match_report(self, match_url: str) -> Optional[dict]:
        """获取比赛战报全文。

        Args:
            match_url: 比赛页面完整 URL，如 https://news.zhibo8.com/.../matchXXXX.htm

        Returns:
            战报 dict，含标题、正文、比分、进球。无可返回 None。
        """
        if not match_url:
            return None

        try:
            html = self._http_get(match_url, referer=self.ZHIBO8_BASE)
            return self._parse_zhibo8_report(html, match_url)
        except ScraperBlockedError:
            raise
        except Exception as e:
            print(f"   ⚠️ 战报解析异常 ({match_url[:60]}): {e}")
            return None

    def scrape_hot_news(self, page: int = 1) -> list[dict]:
        """获取热门体育新闻（从直播吧首页）。

        返回新闻列表，含标题、摘要、URL。
        """
        try:
            html = self._http_get(f"{self.ZHIBO8_BASE}/")
            return self._parse_zhibo8_news(html)
        except Exception as e:
            print(f"   ⚠️ 新闻解析异常: {e}")
            return []

    def scrape_dongqiudi_headlines(self, max_articles: int = 20) -> list[dict]:
        """从懂球帝首页获取文章列表（备源）。

        懂球帝结构稳定，文章链接形如 /articles/6016509.html。
        返回文章标题和URL，正文通过 scrape_dongqiudi_article 懒加载。
        """
        try:
            html = self._http_get(f"{self.DQ_BASE}/", referer=self.DQ_BASE)
            soup = BeautifulSoup(html, "html.parser")
            articles = []
            seen_urls = set()

            for a in soup.find_all("a", href=re.compile(r"/articles/\d+\.html", re.I)):
                href = a.get("href", "")
                text = a.get_text(strip=True)

                if not href or not text or len(text) < 20:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # 拼完整 URL
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = self.DQ_BASE + href
                elif not href.startswith("http"):
                    href = self.DQ_BASE + "/" + href.lstrip("/")

                # 清理标题：去掉前导分类和后缀时间/评论数
                # 懂球帝格式: "足球纽约市长：xxx五洲世界杯07-09 11:15" 或 "01Tyc：xxx22 评论"
                clean_title = re.sub(
                    r'^(?:\d{2})?(?:足球|篮球|电竞|综合|英超|西甲|意甲|德甲|法甲|中超|欧冠|世界杯|五洲|德甲中超|意甲德甲|法甲五洲|英超世界杯|英超意甲|英超德甲|英超五洲)\s*',
                    '', text)
                clean_title = re.sub(
                    r'\s*(?:\d{2}[-:]\d{2}\s*\d+[评评论]*|评论|\d+评论).*$',
                    '', clean_title).strip()
                # 如果清理后太短，用原始文本的前60字
                if len(clean_title) < 8:
                    clean_title = text[:60]

                articles.append({
                    "source": "dongqiudi",
                    "title": clean_title[:80],
                    "url": href,
                    "article_text": "",
                })

                if len(articles) >= max_articles:
                    break

            print(f"   📰 懂球帝文章: {len(articles)} 篇")
            return articles
        except Exception as e:
            print(f"   ⚠️ 懂球帝首页解析异常: {e}")
            return []

    def scrape_dongqiudi_article(self, article_url: str) -> Optional[dict]:
        """从懂球帝获取文章内容（备源）。

        Args:
            article_url: 懂球帝文章 URL，如 https://www.dongqiudi.com/article/123456.html

        Returns:
            文章 dict，含标题、正文。
        """
        if not article_url or "dongqiudi" not in article_url:
            return None
        try:
            html = self._http_get(article_url, referer="https://www.dongqiudi.com/")
            soup = BeautifulSoup(html, "html.parser")
            title_el = soup.find("h1") or soup.find(class_=re.compile(r"title", re.I))
            content_el = self._select_one_fallback(soup, self.DQ_ARTICLE_SELS)
            title = title_el.get_text(strip=True) if title_el else ""
            content = ""
            if content_el:
                for tag in content_el.find_all(["script", "style"]):
                    tag.decompose()
                # 去掉导航栏等非正文区域
                for nav in content_el.find_all(["nav", "header", "footer"]):
                    nav.decompose()
                content = content_el.get_text("\n", strip=True)
                # 去掉首尾的导航文本（懂球帝文章常有"懂球帝首页/动态/..."前缀）
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                # 跳过前几条导航/元数据行
                skip_prefixes = ("懂球帝首页", "动态", "七零", "发布于")
                body_start = 0
                for i, line in enumerate(lines[:8]):
                    if any(line.startswith(p) for p in skip_prefixes):
                        body_start = i + 1
                content = "\n".join(lines[body_start:])
            if title and content:
                return {"source": "dongqiudi", "title": title, "article_text": content}
        except Exception as e:
            print(f"   ⚠️ 懂球帝文章解析异常: {e}")
        return None

    def check_available(self) -> bool:
        """检查直播吧是否可访问。"""
        try:
            html = self._http_get(f"{self.ZHIBO8_BASE}/", check_block=True)
            return "直播吧" in html or "zhibo8" in html
        except Exception:
            return False

    def scrape_football_news(self, date_str: str = None, max_articles: int = 20) -> list[dict]:
        """兼容旧函数名：获取直播吧 NBA 新闻/文章列表。"""
        return self.scrape_basketball_news(date_str=date_str, max_articles=max_articles)

    def scrape_basketball_news(self, date_str: str = None, max_articles: int = 20) -> list[dict]:
        """获取直播吧 NBA 新闻/文章列表（非比赛战报）。

        从 news.zhibo8.com/nba/ 获取指定日期 NBA 新闻文章，
        每篇包含标题、URL、正文内容。

        Args:
            date_str: 日期字符串 YYYY-MM-DD，默认今天
            max_articles: 最多获取的文章数

        Returns:
            list[dict]: 每个 dict 含 title, url, article_text, source
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        try:
            html = self._http_get(f"{self.ZHIBO8_NEWS}/nba/")
            soup = BeautifulSoup(html, "html.parser")

            articles = []
            seen_urls = set()

            # news 页的文章链接形如: /zuqiu/2026-07-09/6a4e200503b0fnative.htm（降级链适配改版）
            for a in self._find_all_fallback_regex(soup, self.ZHIBO8_NEWS_LINK_SELS):
                href = a.get("href", "")
                title = a.get_text(strip=True)

                if not href or not title or len(title) < 15:
                    continue
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                # 拼完整 URL
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = self.ZHIBO8_NEWS + href
                elif not href.startswith("http"):
                    href = self.ZHIBO8_NEWS + "/" + href.lstrip("/")

                # 只取当天文章
                if date_str not in href:
                    continue

                articles.append({
                    "source": "zhibo8",
                    "title": title[:80],
                    "url": href,
                    "article_text": "",  # 需要单独抓取
                })

                if len(articles) >= max_articles:
                    break

            # 懒加载正文：先返回标题/URL，爬取时按需取正文
            if len(articles) > 0:
                print(f"   📰 直播吧NBA新闻: {len(articles)} 篇", file=sys.stderr)
            return articles

        except Exception as e:
            print(f"   ⚠️ 直播吧新闻解析异常: {e}")
            return []

    def scrape_zhibo8_article_content(self, url: str) -> Optional[str]:
        """获取直播吧文章/战报正文内容。

        复用 scrape_match_report 的解析逻辑(.content 容器)。
        """
        report = self.scrape_match_report(url)
        if report:
            return report.get("article_text", "")
        return None

    def scrape_zhibo8_schedule(self, date_str: str) -> list[dict]:
        """获取指定日期的赛程列表（未来未开始的比赛）。

        从直播吧首页解析比赛列表，返回所有未开始（PRE 状态）的比赛。
        用于赛前预测场景，在晚间批次采集次日赛程。

        Args:
            date_str: 日期字符串 YYYY-MM-DD（目标日期，通常为明日）

        Returns:
            list[dict]: 未开始的比赛列表，每条含 league, home_team, away_team,
                       status, utc_date 等字段
        """
        try:
            html = self._http_get(f"{self.ZHIBO8_BASE}/")
            matches = self._parse_zhibo8_homepage(html, date_str)
            future = [m for m in matches if m.get("status") == "PRE"]
            if future:
                self._consecutive_blocks = 0
                print(f"   📅 未来赛程: {len(future)} 场未开始的比赛")
                for m in future:
                    utc = m.get("utc_date", "")
                    print(f"      [{m.get('league', '?')}] {m['home_team']} vs {m['away_team']} ({utc})")
            return future
        except ScraperBlockedError:
            self._consecutive_blocks += 1
            raise
        except Exception as e:
            print(f"   ⚠️ 获取赛程异常: {e}")
            return []

    # ------------------------------------------------------------------
    #  直播吧 — 赛程页解析
    # ------------------------------------------------------------------

    def _parse_zhibo8_homepage(self, html: str, date_str: str) -> list[dict]:
        """解析直播吧首页，提取当天比赛和战报链接。

        直播吧首页有两种比赛链接：
        1. 直播链接 (zhibo.xxx) — 无比分，纯直播
        2. 战报链接 (news.zhibo8.com/.../matchXXX.htm) — 有比分和标题

        我们两种都取，优先取战报链接。
        选择器通过降级链配置，网站HTML改版时自动适配。
        """
        soup = BeautifulSoup(html, "html.parser")
        matches = []
        seen_urls = set()

        # 方法1：从 schedule 容器找比赛链接（降级链适配改版）
        schedule = self._select_one_fallback(soup, self.ZHIBO8_SCHEDULE_SELS)
        # fallback: 也尝试通过 class 名正则匹配
        if not schedule:
            schedule = soup.find(class_=re.compile(r"schedule|match|contest", re.I))
        if schedule:
            # 只解析带 data-type/league 标签的条目；全站链接无法可靠区分NBA与WNBA。
            for li in self._find_all_fallback(schedule, self.ZHIBO8_FOOTBALL_ITEM_SELS):
                self._parse_football_li(li, date_str, matches, seen_urls)

        # 不从全页新闻标题反推比赛：普通NBA新闻中的金额（如300-400万）
        # 很容易被误识别为比分。比赛只以带赛事标签的 schedule 条目为准。

        # 只保留 NBA；直播吧同一 data-type 下还有 CBA、WNBA、FIBA 等赛事。
        matches[:] = [m for m in matches if m.get("league") == "NBA"]

        return matches

    def _parse_football_li(self, li, date_str: str, matches: list, seen_urls: set):
        """兼容旧函数名：从 basketball 条目解析 NBA 比赛信息。"""

        # 取赛事名，并在解析入口排除非 NBA 篮球赛事。
        league_el = self._select_one_fallback(li, self.ZHIBO8_LEAGUE_SELS)
        league_cn = league_el.get_text(strip=True) if league_el else ""
        label = li.get("label", "") or ""
        league_label = (league_cn + " " + label).upper()
        if "WNBA" in league_label or not re.search(r"(?<![A-Z])NBA(?![A-Z])", league_label):
            return
        league = "NBA"

        # 取队名（按分隔符拆分）
        teams_el = self._select_one_fallback(li, self.ZHIBO8_TEAMS_SELS)
        home_team = away_team = ""
        home_score = away_score = None
        if teams_el:
            teams_text = teams_el.get_text(" ", strip=True)
            scored = re.search(r"(.+?)\s+(\d{2,3})\s*[-–:]\s*(\d{2,3})\s+(.+)", teams_text)
            if scored:
                home_team, home_score, away_score, away_team = scored.group(1), int(scored.group(2)), int(scored.group(3)), scored.group(4)
            else:
                sep = re.search(r'\s+(?:-|–|vs|VS|vs\.)\s+', teams_text)
                if sep:
                    home_team = teams_text[:sep.start()].strip()
                    away_team = teams_text[sep.end():].strip()
            home_team = re.sub(r'^[^0-9A-Za-z一-鿿]+|[^0-9A-Za-z一-鿿]+$', '', home_team)
            away_team = re.sub(r'^[^0-9A-Za-z一-鿿]+|[^0-9A-Za-z一-鿿]+$', '', away_team)

        # 取比赛链接（取第一个含 "match" 的 href）
        match_url = ""
        for a in li.find_all("a", href=re.compile(r"match", re.I)):
            href = a.get("href", "")
            if not href:
                continue
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                if "news" in href:
                    href = self.ZHIBO8_NEWS + href
                else:
                    href = self.ZHIBO8_BASE + href
            elif not href.startswith("http"):
                href = self.ZHIBO8_NEWS + "/" + href.lstrip("/")
            match_url = href
            break

        if not home_team or not away_team or not match_url:
            return
        if match_url in seen_urls:
            return
        seen_urls.add(match_url)

        league_en = "NBA"

        # 提取 data-time 属性（如 "2026-07-14 04:00"），用于赛程预测
        utc_date = li.get("data-time", "")

        match = {
            "source": "zhibo8",
            "match_url": match_url,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "status": "FT" if home_score is not None else "PRE",
            "league": league_en,
            "match_date": date_str,
            "utc_date": utc_date,
        }

        # 去重：避免与 _process_match_link 已提取的重复
        key = (home_team, away_team)
        if not any(m["home_team"] == home_team and m["away_team"] == away_team for m in matches):
            matches.append(match)

    def _process_match_link(self, a, date_str: str, matches: list, seen_urls: set):
        """处理单个比赛链接，尝试解析为 match dict。"""
        href = a.get("href", "")
        text = a.get_text(strip=True)

        if not href or href in seen_urls:
            return
        if "/nba/" not in href.lower() and "NBA" not in text.upper():
            return
        seen_urls.add(href)

        # 拼接完整 URL
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/") and "news" in href:
            href = self.ZHIBO8_NEWS + href
        elif href.startswith("/"):
            href = self.ZHIBO8_BASE + href
        elif not href.startswith("http"):
            href = self.ZHIBO8_NEWS + "/" + href.lstrip("/")

        match = self._parse_match_from_link_text(text, href, date_str)
        if match:
            # Avoid duplicates
            key = (match["home_team"], match["away_team"])
            if not any(m["home_team"] == match["home_team"] and m["away_team"] == match["away_team"] for m in matches):
                matches.append(match)

    def _parse_match_from_link_text(self, text: str, url: str, date_str: str) -> Optional[dict]:
        """从链接文本中解析比赛信息。

        处理格式:
        - "巴西2-1绝杀日本" → home=巴西, score=2-1, away=日本
        - "德国点球大战4-5遭巴拉圭淘汰" → ...
        - "阿根廷vs巴西" → 无比分（未开始）
        """
        if not text:
            return None

        # 规范化比分周围空格：新版zhibo8首页<a>标签内用子div渲染队名和比分，
        # get_text(strip=True) 会保留元素间的空格，得到 "阿根廷3 - 2埃及"(空格导致正则失败)
        text = re.sub(r'\s*([-–:—])\s*', r'\1', text)
        # 也处理 "3 - 2" 中 dash 前后都有空格的情况(上一步已覆盖此case)

        # 尝试提取比分 (X-Y 格式)
        score_m = re.search(r"(\d+)[-–:](\d+)", text)
        home_score = away_score = None
        status = "PRE"

        if score_m:
            home_score = int(score_m.group(1))
            away_score = int(score_m.group(2))
            status = "FT"  # 有比分通常是已结束

        # 提取双方队名（通过比分的前后文或 "vs" 分隔）
        home_team = ""
        away_team = ""

        if score_m:
            # 比分之前的文本是主队，之后是客队
            before = text[:score_m.start()].strip()
            after = text[score_m.end():].strip()

            # 去掉比分两边的非中文字符
            # 主队：从末尾往前找最后一个中文队名
            # 去掉比分前的中性描述词（非队名）
            home_suffixes = ["点球大战", "点球", "加时", "客场", "主场"]
            before_clean = before
            for suffix in home_suffixes:
                if before_clean.endswith(suffix):
                    before_clean = before_clean[:-len(suffix)]
                    break
            # 去前缀（标题性前缀如 "晋级16强！" "爆冷！"）
            # 去掉所有非队名前缀：以非中文开头的部分
            home_prefix_match = re.match(r"^[^一-鿿]+", before_clean)
            if home_prefix_match:
                before_clean = before_clean[home_prefix_match.end():]
            home_prefixes = ["爆冷", "大冷", "再爆冷"]
            for prefix in home_prefixes:
                if before_clean.startswith(prefix):
                    before_clean = before_clean[len(prefix):]
                    break
            home_match = re.search(r"([一-鿿]{2,6})$", before_clean)
            if home_match:
                home_team = home_match.group(1)

            # 客队：去掉常见前缀后找第一个中文队名
            away_prefixes = ["绝杀", "点杀", "逆转", "爆冷", "遭", "被",
                             "力克", "大胜", "小胜", "险胜", "战平", "逼平",
                             "横扫", "完胜", "击退", "斩杀", "淘汰",
                             "淘汰出局", "拒", "止步"]
            after_clean = after
            # 去掉比分和队名之间的描述词，以及管道符分隔的额外比分信息
            first_pipe = after.find("|")
            if first_pipe > 0:
                after = after[:first_pipe]
            for mid in ["点球大战", "点球", "加时赛", "加时"]:
                if after_clean.startswith(mid):
                    after_clean = after_clean[len(mid):]
                    break
            for prefix in away_prefixes:
                if after_clean.startswith(prefix):
                    after_clean = after_clean[len(prefix):]
                    break
            away_match = re.search(r"^([一-鿿]{2,6})", after_clean)
            if away_match:
                away_team = away_match.group(1)
                # 去掉队名后的非队名后缀
                for suffix in ["淘汰", "淘汰出局", "绝杀", "出局", "噩梦", "点球", "加时"]:
                    if away_team.endswith(suffix):
                        away_team = away_team[:-len(suffix)]
                        break
                # 也去掉多余的管道分隔符(compact score format中的冲突字符)
                away_team = away_team.split("|")[0].strip()
        else:
            # 无比分，找 "vs" 或 "VS"
            vs_m = re.search(r"(.{2,6})\s*v[ssVS]\s*(.{2,6})", text)
            if vs_m:
                home_team = vs_m.group(1).strip()
                away_team = vs_m.group(2).strip()

        # 队名清理：去掉常见后缀
        for team in [home_team, away_team]:
            for suffix in ["直播", "视频", "录像", "回放", "集锦", "战报"]:
                if suffix in team:
                    return None  # 不是纯比赛链接

        if not home_team or not away_team:
            return None

        # 推断联赛名（从 URL 或上下文）
        league = self._infer_league(text, url)

        return {
            "source": "zhibo8",
            "match_url": url,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "status": status,
            "league": league,
            "match_date": date_str,
        }

    def _infer_league(self, text: str, url: str) -> str:
        """仅识别 NBA，避免把 CBA/WNBA/FIBA 混入内容池。"""
        combined = f"{text} {url}".upper()
        if "WNBA" in combined:
            return ""
        return "NBA" if re.search(r"(?<![A-Z])NBA(?![A-Z])", combined) else ""

    # ------------------------------------------------------------------
    #  直播吧 — 战报页解析
    # ------------------------------------------------------------------

    def _parse_zhibo8_report(self, html: str, url: str) -> Optional[dict]:
        """解析直播吧战报页面，提取标题+正文+比分。"""
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        title_el = soup.find("h1") or soup.find("title")
        if title_el:
            title = title_el.get_text(strip=True)
            # 去掉站点名后缀
            for suffix in ["-直播吧", "_直播吧", "|直播吧"]:
                if suffix in title:
                    title = title.split(suffix)[0].strip()

        # 正文（降级链适配改版）
        content_el = self._select_one_fallback(soup, self.ZHIBO8_CONTENT_SELS) or soup.find(class_=re.compile(r"content|article|detail|news", re.I))
        content = ""
        if content_el:
            for tag in content_el.find_all(["script", "style", "iframe"]):
                tag.decompose()
            content = content_el.get_text("\n", strip=True)

        if not content:
            return None

        # 从标题中提取比分
        home_team = away_team = ""
        home_score = away_score = None
        score_m = re.search(r"(\d+)[-–:](\d+)", title)
        if score_m:
            home_score = int(score_m.group(1))
            away_score = int(score_m.group(2))
            # 提取队名
            before = title[:score_m.start()].strip()
            after = title[score_m.end():].strip()
            hm = re.search(r"([一-鿿]{2,6})$", before)
            am = re.search(r"^([一-鿿]{2,6})", after)
            if hm:
                home_team = hm.group(1)
            if am:
                away_team = am.group(1)

        # 从正文提取明确出现的球员基础数据，供事实校验和写作使用。
        player_stats = self._extract_player_stats_from_text(content)

        # 从战报中提取配图
        images = []
        if content_el:
            seen_urls = set()
            for img in content_el.find_all("img"):
                src = img.get("src", "")
                if src and src.startswith("http") and src not in seen_urls:
                    # 过滤掉头像、icon等小图
                    w = img.get("width", "0")
                    if w.isdigit() and int(w) < 100:
                        continue
                    seen_urls.add(src)
                    images.append({"url": src, "source": "zhibo8"})

        # 从 URL/内容推断联赛
        league = self._infer_league(title + url, url)

        return {
            "source": "zhibo8",
            "match_url": url,
            "article_title": title,
            "article_text": content,
            "home_team": home_team,
            "away_team": away_team,
            "home_score": home_score,
            "away_score": away_score,
            "league": league,
            "goals": [],  # 兼容旧数据结构
            "player_stats": player_stats,
            "data_confidence": "high",
            "images": images,
        }

    @staticmethod
    def _extract_goals_from_text(text: str, home_team: str, away_team: str) -> list[dict]:
        """从战报正文提取进球信息。

        通过常见进球描述模式提取，如:
        - "卡塞米罗头球破门"
        - "马丁内利95分钟绝杀"
        - "佐野海舟贴地斩首开记录"
        """
        goals = []
        # 模式: 球员名 + 分钟 + 动作
        goal_patterns = [
            r"([一-鿿]{2,4})(\d+)['′]?(?:分钟)?(?:头球|破门|绝杀|进球|抽射|推射|远射|点射|补射|铲射|垫射)",
            r"(\d+)['′]?(?:分钟)?([一-鿿]{2,4})(?:头球|破门|绝杀|进球)",
            r"([一-鿿]{2,4})(?:梅开二度|独中两元|帽子戏法)",
            r"(\d+)['′]?(?:分钟)?(?:点球|点射).*?([一-鿿]{2,4})",
        ]

        for pattern in goal_patterns:
            for m in re.finditer(pattern, text):
                # 提取球员和分钟
                if m.lastindex >= 2:
                    # Try to identify which is minute and which is player
                    groups = [g for g in m.groups() if g]
                    player = ""
                    minute = None
                    for g in groups:
                        if g.isdigit():
                            minute = int(g)
                        elif re.match(r"^[一-鿿]+$", g):
                            player = g
                else:
                    player = m.group(1) if re.match(r"^[一-鿿]+$", m.group(1)) else ""
                    minute = int(m.group(1)) if m.group(1).isdigit() else None

                if not player:
                    continue

                # 判断主客队
                team = "home"
                if away_team and away_team in text:
                    # Check context around player name
                    idx = text.find(player)
                    context = text[max(0, idx - 50):idx + 50]
                    if away_team in context:
                        team = "away"

                # 避免重复
                is_dup = any(g["scorer"] == player and g["minute"] == minute for g in goals)
                if not is_dup:
                    goals.append({
                        "minute": minute,
                        "scorer": player,
                        "scorer_team": team,
                        "type": "GOAL",
                    })

        return goals

    @staticmethod
    def _extract_player_stats_from_text(text: str) -> list[dict]:
        """提取“球员 得分/篮板/助攻”类明确技术统计，不做推测。"""
        stats = []
        seen = set()
        patterns = [
            r"([一-鿿·-]{2,12}?)(?:得到|拿到|砍下|贡献)\s*(\d{1,2})分(?:\s*(\d{1,2})篮板)?(?:\s*(\d{1,2})助攻)?",
            r"([一-鿿·-]{2,12})\s+(\d{1,2})分(?:\s*(\d{1,2})篮板)?(?:\s*(\d{1,2})助攻)?",
            r"([一-鿿·-]{2,12})\s*(\d{1,2})分[、+](\d{1,2})板[、+](\d{1,2})助",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip("，。；：、 ")
                if name in seen or any(word in name for word in ("全队", "球队", "比赛", "末节")):
                    continue
                seen.add(name)
                groups = match.groups()
                stats.append({
                    "player": name,
                    "points": int(groups[1]),
                    "rebounds": int(groups[2]) if len(groups) > 2 and groups[2] else None,
                    "assists": int(groups[3]) if len(groups) > 3 and groups[3] else None,
                })
        return stats[:20]

    # ------------------------------------------------------------------
    #  直播吧 — 新闻解析
    # ------------------------------------------------------------------

    def _parse_zhibo8_news(self, html: str) -> list[dict]:
        """从直播吧首页提取新闻链接。"""
        soup = BeautifulSoup(html, "html.parser")

        # 找新闻区域
        news_links = soup.find_all("a", href=re.compile(r"article|news", re.I))
        seen = set()
        news = []
        for a in news_links:
            href = a.get("href", "")
            text = a.get_text(strip=True)
            if not text or len(text) < 10:
                continue
            if href in seen:
                continue
            seen.add(href)

            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = self.ZHIBO8_BASE + href

            news.append({
                "title": text[:80],
                "url": href,
                "source": "zhibo8",
            })

        return news

    # ------------------------------------------------------------------
    #  降级：从战报页反推比赛（当天无赛程时的备源）
    # ------------------------------------------------------------------

    def _scrape_matches_from_reports(self, date_str: str) -> list[dict]:
        """从直播吧新闻区反推当天比赛。

        当赛程页没有比赛列表时，从首页新闻链接中找比赛战报。
        """
        try:
            html = self._http_get(f"{self.ZHIBO8_BASE}/")
            soup = BeautifulSoup(html, "html.parser")
            links = soup.find_all("a", href=re.compile(r"match\d+.*\.htm", re.I))

            matches = []
            seen = set()
            for a in links:
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if not href or href in seen:
                    continue
                seen.add(href)

                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = self.ZHIBO8_BASE + href
                elif not href.startswith("http"):
                    href = self.ZHIBO8_NEWS + "/" + href.lstrip("/")

                match = self._parse_match_from_link_text(text, href, date_str)
                if match:
                    matches.append(match)

            return matches
        except Exception:
            return []

    # ------------------------------------------------------------------
    #  HTTP 请求层
    # ------------------------------------------------------------------

    def _http_get(self, url: str, referer: str = None, check_block: bool = False) -> str:
        """带反爬措施的 HTTP GET 请求。"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.REQUEST_DELAY:
            time.sleep(self.REQUEST_DELAY - elapsed)

        last_error = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                headers = {
                    "User-Agent": self._current_ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                }
                if referer:
                    headers["Referer"] = referer

                resp = self.session.get(url, headers=headers, timeout=self.TIMEOUT)
                self._last_request_time = time.time()

                if resp.status_code == 200:
                    # Auto-detect encoding: many Chinese sites serve UTF-8 but
                    # declare ISO-8859-1 in headers, causing garbled text
                    if "zhibo8" in url:
                        resp.encoding = "utf-8"
                    elif resp.encoding and resp.encoding.lower() == "iso-8859-1":
                        resp.encoding = resp.apparent_encoding or "utf-8"
                    text = resp.text
                    if not check_block:
                        block_indicators = ["验证", "访问频率", "captcha"]
                        for ind in block_indicators:
                            if ind in text:
                                raise ScraperBlockedError(f"触发封禁: {ind}")
                    return text
                elif resp.status_code == 403:
                    raise ScraperBlockedError(f"HTTP 403")
                elif resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", str(self.BACKOFF_BASE ** attempt)))
                    time.sleep(wait)
                    continue
                elif resp.status_code == 404:
                    return ""

            except requests.Timeout:
                last_error = f"timeout after {self.TIMEOUT}s"
            except requests.ConnectionError as e:
                last_error = f"connection error: {e}"
            except ScraperBlockedError:
                raise
            except Exception as e:
                last_error = str(e)

            if attempt < self.MAX_RETRIES:
                time.sleep(self.BACKOFF_BASE ** attempt + random.uniform(0, 0.5))
                self._rotate_ua()

        if last_error:
            raise requests.RequestException(last_error)
        return ""

    # ------------------------------------------------------------------
    #  UA 轮换
    # ------------------------------------------------------------------

    @property
    def _current_ua(self) -> str:
        return getattr(self, "__ua", self.USER_AGENTS[0])

    def _rotate_ua(self):
        self.__ua = random.choice(self.USER_AGENTS)
