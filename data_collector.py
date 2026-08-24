#!/usr/bin/env python3
"""NBA 自媒体 — 数据采集模块

负责: 比赛数据采集、公众号爆款趋势、积分榜/射手榜、图片搜索。
"""

import os, json, sys, subprocess, requests, time, re
from urllib.parse import urlparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from constants import (PROJECT_ROOT, OUTPUT_DIR, GZH_SCRIPT,
                       FOOTBALL_DATA_KEY, FOOTBALL_DATA_BASE,
                       COMPETITION_IDS, GZH_KEYWORD_GROUPS, GZH_TRANSFER_KEYWORDS,
                       GZH_NOISE_PATTERNS, WIKI_PLAYERS, WIKI_TEAMS, FOOTYRENDERS_PLAYERS,
                       UNSPLASH_KEY, NBA_STANDINGS_URL, NBA_PLAYERS_URL,
                       WORLD_NEWS_API_KEY, WORLD_NEWS_URL)

from utils import retry


# ============================================================
# Data Collection
# ============================================================


def collect_real_matches(date_str, batch_mode="morning"):
    """早晚读取头条AI话题，中午采集财经/科技新闻。"""
    if batch_mode == "noon":
        return _collect_finance_news(date_str, batch_mode)
    return _collect_toutiao_ai_topic(date_str, batch_mode)


def _collect_toutiao_ai_topic(date_str, batch_mode):
    from playwright.sync_api import sync_playwright
    auth_file = Path(os.environ.get("TOUTIAO_AUTH_FILE", PROJECT_ROOT / "toutiao_auth.json"))
    if not auth_file.exists():
        raise RuntimeError("缺少头条登录状态，无法读取AI创作建议")
    publish_url = "https://mp.toutiao.com/profile_v4/graphic/publish"
    topic = ""
    with sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(headless=True,
                args=["--disable-blink-features=AutomationControlled"])
        except Exception:
            browser = playwright.chromium.launch(channel="chrome", headless=True,
                args=["--disable-blink-features=AutomationControlled"])
        context = browser.new_context(storage_state=str(auth_file), locale="zh-CN")
        page = context.new_page()
        page.goto(publish_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)
        if "/auth/" in page.url or "/login" in page.url:
            browser.close()
            raise RuntimeError("头条登录状态已过期")
        locator = page.locator(".recommend-list .topic .text").first
        topic = (locator.inner_text(timeout=10000) or "").strip()
        browser.close()
    if not topic:
        raise RuntimeError("头条第一条AI创作建议为空")
    print(f"[1/5] 头条AI创作建议第一条：{topic}")
    article = {
        "article_id": f"toutiao-{date_str}-{batch_mode}-{topic}",
        "title": topic, "url": publish_url, "article_text": topic,
        "source": "头条创作助手", "source_kind": "toutiao_ai", "source_images": [],
        "category": "topic", "region": "cn", "_content_type_hint": "AI话题",
    }
    return {"date": date_str, "total_matches": 0, "fixtures_by_league": {},
            "all_fixtures": [], "standings": {}, "data_source": "toutiao_ai",
            "batch_mode": batch_mode, "media_reports": {},
            "news_articles": [article], "transfer_news": []}


def _collect_finance_news(date_str, batch_mode):
    if not WORLD_NEWS_API_KEY:
        raise RuntimeError("缺少 WORLD_NEWS_API_KEY")
    region = "overseas" if batch_mode == "noon" else "cn"
    params = {"categories": "business,technology", "number": 10, "sort": "publish-time"}
    if region == "cn":
        params.update({"source-countries": "cn", "language": "zh"})
    else:
        params.update({"source-countries": "us,gb,ca,au", "language": "en"})
    response = requests.get(WORLD_NEWS_URL, headers={"x-api-key": WORLD_NEWS_API_KEY},
                            params=params, timeout=30)
    response.raise_for_status()
    rows = response.json().get("news") or []
    overseas_terms = ("china", "chinese", "ai", "semiconductor", "chip", "electric vehicle",
                      "automaker", "consumer", "retail", "manufacturing", "supply chain", "factory",
                      "apple", "tesla", "nvidia", "microsoft", "google", "amazon", "meta", "tiktok")
    articles = []
    for raw in rows:
        title = str(raw.get("title") or "").strip()
        text = str(raw.get("text") or "").strip()
        url = str(raw.get("url") or "").strip()
        category = str(raw.get("category") or "").lower()
        host = re.sub(r"^www\.", "", urlparse(url).hostname or "").lower()
        combined = f" {title} {text} {host} ".lower()
        if not title or not text or not url:
            continue
        if category not in ("business", "technology"):
            continue
        if region == "overseas" and not any(term in combined for term in overseas_terms):
            continue
        articles.append({
            "article_id": str(raw.get("id") or url), "title": title, "url": url,
            "article_text": text, "source": host, "source_images": [],
            "category": category, "region": region,
            "_content_type_hint": "科技动态" if category == "technology" else ("海外商业" if region == "overseas" else "国内商业"),
        })
    print(f"[1/5] 采集财经新闻 ({date_str}, {region})：通过 {len(articles)}/{len(rows)} 条")
    return {"date": date_str, "total_matches": 0, "fixtures_by_league": {},
            "all_fixtures": [], "standings": {}, "data_source": "worldnews",
            "batch_mode": batch_mode, "media_reports": {},
            "news_articles": articles, "transfer_news": []}


def _collect_real_matches_nba(date_str):
    """保留原NBA采集实现，财经入口不再调用。"""
    print(f"[1/5] 采集 NBA 比赛与新闻 ({date_str})...")
    from media_scraper import SportsScraper

    scraper = SportsScraper()
    try:
        result = _collect_from_media(scraper, date_str)
    except Exception as exc:
        print(f"   ⚠️ 直播吧NBA采集异常: {exc}")
        result = {"date": date_str, "total_matches": 0, "fixtures_by_league": {},
                  "all_fixtures": [], "standings": {}, "data_source": "zhibo8",
                  "media_reports": {}, "news_articles": [], "transfer_news": []}

    try:
        result["standings"] = fetch_recent_standings()
        result["transfer_news"] = collect_transfer_news(date_str)
    except Exception as exc:
        print(f"   ⚠️ NBA榜单/交易素材采集异常: {exc}")
    return result


def collect_transfer_news(date_str):
    """独立采集 NBA 交易、签约与自由球员新闻。

    供“交易雷达”等栏目使用，与比赛数据管线并行。

    Returns:
        list[dict]: 交易新闻列表，每条含 title, url, article_text, source, _content_type_hint
    """
    print(f"[数据] 采集NBA交易新闻 ({date_str})...")
    from media_scraper import SportsScraper
    transfer_keywords = ("交易", "签约", "续约", "加盟", "买断", "裁掉", "裁员",
                         "自由球员", "合同", "顶薪", "底薪", "选秀", "签换", "主教练")
    articles = []
    seen_titles = set()

    # 从直播吧采集新闻文章
    try:
        scraper = SportsScraper()
        news = scraper.scrape_basketball_news(date_str, max_articles=30)
        for art in news or []:
            title = (art.get("title", "") or "").strip()
            if not title or title in seen_titles:
                continue
            # 检查标题是否包含转会关键词
            if any(kw in title for kw in transfer_keywords):
                seen_titles.add(title)
                article_text = art.get("article_text", "") or art.get("_content", "") or ""
                articles.append({
                    "title": title,
                    "url": art.get("url", ""),
                    "article_text": article_text,
                    "source": "zhibo8",
                    "_content_type_hint": "交易资讯",
                })
    except Exception as e:
        print(f"   ⚠️ 直播吧交易新闻采集异常: {e}")

    if articles:
        print(f"   🔍 NBA交易新闻: {len(articles)} 篇")
        for a in articles[:5]:
            print(f"      - {a['title'][:45]}")
    else:
        print("   ℹ️ 暂未发现NBA交易新闻")
    return articles


def collect_future_matches(date_str, days_ahead=1):
    """采集未来比赛数据用于赛前预测。

    使用 media_scraper.SportsScraper 的 scrape_zhibo8_schedule() 方法
    从直播吧首页获取未来赛程，返回未开始的比赛列表。

    Args:
        date_str: 当前日期 YYYY-MM-DD
        days_ahead: 预测哪一天的比赛，默认1（明日）

    Returns:
        list[dict]: 未来比赛列表，每条含 home_team, away_team, league, status, utc_date
    """
    target_date = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=days_ahead)
    target_str = target_date.strftime("%Y-%m-%d")

    from media_scraper import SportsScraper
    try:
        scraper = SportsScraper()
        if not scraper.check_available():
            print("   ⚠️ 直播吧不可达，无法获取赛程")
            return []

        future_matches = scraper.scrape_zhibo8_schedule(target_str)
        if future_matches:
            print(f"   ✅ 赛前预测素材: {len(future_matches)} 场未来比赛 ({target_str})")
        else:
            print(f"   ℹ️ 明日 ({target_str}) 无赛程，跳过赛前预测")
        return future_matches
    except Exception as e:
        print(f"   ⚠️ 获取未来赛程异常: {e}")
        return []


def _collect_from_media(scraper, date_str):
    """从媒体源（直播吧）采集比赛数据，并用战报内容丰富数据。

    返回格式与 collect_real_matches 兼容：
    {
        "date": str, "total_matches": int,
        "fixtures_by_league": dict,
        "all_fixtures": list[dict],
        "standings": dict,
        "data_source": str,
        "media_reports": dict,  # match_id → report dict
    }
    """
    matches = scraper.scrape_today_matches(date_str)

    # 获取每场比赛的战报全文
    fixture_details = []
    media_reports = {}

    for m in matches:
        report_text = ""
        player_stats = []
        source_images = []
        match_url = m.get("match_url", "")

        # 获取战报
        if match_url:
            try:
                report = scraper.scrape_match_report(match_url)
                if report:
                    report_text = report.get("article_text", "")
                    player_stats = report.get("player_stats", [])
                    source_images = report.get("images", [])
                    # 从战报中提取联赛名
                    if not m.get("league") and report.get("league"):
                        m["league"] = report["league"]
                    if m.get("home_score") is None and report.get("home_score") is not None:
                        m["home_score"] = report["home_score"]
                        m["away_score"] = report["away_score"]
                        m["status"] = "FT"
            except Exception as e:
                print(f"   ⚠️ 战报获取失败 ({m['home_team']} vs {m['away_team']}): {e}")

        fixture = {
            "id": f"zhibo8_{m['home_team']}_{m['away_team']}",
            "source": "zhibo8",
            "source_url": match_url,
            "league": m.get("league", ""),
            "home_team": m["home_team"],
            "away_team": m["away_team"],
            "home_score": m.get("home_score"),
            "away_score": m.get("away_score"),
            "status": m.get("status", "FT"),
            "utc_date": date_str,
            "goals": [],
            "player_stats": player_stats,
            "article_text": report_text,
            "source_images": source_images,
            "data_confidence": "high",
        }
        fixture_details.append(fixture)

        if report_text:
            media_reports[fixture["id"]] = fixture

    # 按联赛分组
    by_league = defaultdict(list)
    for f in fixture_details:
        league = f.get("league", "未知赛事")
        by_league[league].append(f)

    print(f"   📄 直播吧战报: {len(media_reports)}/{len(fixture_details)} 场有详细战报")

    result = {
        "date": date_str,
        "total_matches": len(fixture_details),
        "fixtures_by_league": dict(by_league),
        "all_fixtures": fixture_details,
        "standings": {},
        "data_source": "zhibo8",
        "media_reports": media_reports,
        "news_articles": [],  # 新闻文章兜底
    }

    # 平行采集直播吧新闻文章（作为补充素材，不依赖战报数量）
    try:
        news_articles = scraper.scrape_basketball_news(date_str, max_articles=15)
        result["news_articles"] = news_articles
        if news_articles:
            print(f"   📰 直播吧新闻: {len(news_articles)} 篇")
    except Exception as e:
        print(f"   ⚠️ 新闻采集异常: {e}")

    return result


def _collect_from_dongqiudi(scraper, date_str):
    """从懂球帝采集新闻文章。

    与直播吧平行采集，返回格式与 collect_real_matches 兼容，
    data_source = "dongqiudi"。
    """
    headlines = scraper.scrape_dongqiudi_headlines(max_articles=15)
    if not headlines:
        return {"date": date_str, "total_matches": 0, "fixtures_by_league": {},
                "all_fixtures": [], "standings": {}, "data_source": "media"}

    # 取每篇文章正文
    fixture_details = []
    for art in headlines:
        url = art.get("url", "")
        title = art.get("title", "")
        try:
            result = scraper.scrape_dongqiudi_article(url)
            article_text = result.get("article_text", "") if result else ""
        except Exception:
            article_text = ""

        fixture = {
            "id": f"dongqiudi_{hash(url) % 1000000:06d}",
            "source": "dongqiudi",
            "source_url": url,
            "league": "",
            "home_team": "", "away_team": "",
            "home_score": None, "away_score": None,
            "status": "NEWS",
            "utc_date": date_str,
            "goals": [],
            "article_text": article_text,
            "article_title": title,
            "source_images": [],
            "data_confidence": "high",
        }
        fixture_details.append(fixture)

    print(f"   ✅ 懂球帝文章: {len(fixture_details)} 篇, "
          f"{sum(1 for f in fixture_details if f.get('article_text'))} 篇有正文")

    return {
        "date": date_str,
        "total_matches": len(fixture_details),
        "fixtures_by_league": {},
        "all_fixtures": fixture_details,
        "standings": {},
        "data_source": "dongqiudi",
        "media_reports": {},
        "news_articles": [],
    }


def _collect_from_football_data(date_str):
    """从 football-data.org 采集比赛数据（备用源）。"""
    headers = {"X-Auth-Token": FOOTBALL_DATA_KEY}
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    weekday = target_date.weekday()
    if weekday == 6:
        from_date = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")
    elif weekday == 0:
        from_date = (target_date - timedelta(days=2)).strftime("%Y-%m-%d")
    else:
        from_date = date_str
    to_date = date_str
    print(f"   查询范围: {from_date} ~ {to_date}")

    all_matches = []
    for league_name, comp_id in COMPETITION_IDS.items():
        try:
            def _fetch():
                resp = requests.get(f"{FOOTBALL_DATA_BASE}/competitions/{comp_id}/matches",
                                   params={"dateFrom": from_date, "dateTo": to_date},
                                   headers=headers, timeout=15)
                resp.raise_for_status()
                return resp.json().get("matches", [])
            matches = retry(_fetch, max_retries=2, base_delay=1, desc=f"football-data({league_name})")
            if matches:
                print(f"   {league_name}: {len(matches)} 场")
            all_matches.extend(matches)
            time.sleep(0.6)
        except Exception as e:
            print(f"   {league_name}: error - {e}")

    seen_ids = set()
    unique = []
    for m in all_matches:
        if m.get("id") not in seen_ids:
            seen_ids.add(m.get("id"))
            unique.append(m)

    relevant = []
    fixture_details = []
    valid_comps = {"Premier League", "Primera Division", "Serie A", "Bundesliga",
                   "Ligue 1", "UEFA Champions League", "Campeonato Brasileiro Série A",
                   "FIFA World Cup"}
    for m in unique:
        comp = m.get("competition", {}).get("name", "")
        if comp in valid_comps:
            relevant.append(m)
            score = m.get("score", {}).get("fullTime", {})
            hg = score.get("home")
            ag = score.get("away")
            fixture = {
                "id": m.get("id"),
                "league": comp, "home_team": m.get("homeTeam", {}).get("name", ""),
                "away_team": m.get("awayTeam", {}).get("name", ""),
                "home_score": hg, "away_score": ag,
                "status": m.get("status"), "matchday": m.get("matchday"),
                "utc_date": m.get("utcDate", ""),
                "goals": [],  # will be filled below if available
            }
            fixture_details.append(fixture)

    # Step 1b: Nullify scores for non-finished matches
    # Football-data.org score.fullTime may contain placeholder or stale data
    # for IN_PLAY/PRE matches. Only FT/AET/PEN status scores are reliable.
    FINISHED_STATUSES = {"FT", "AET", "PEN"}
    non_finished = 0
    for f in fixture_details:
        if f.get("status") not in FINISHED_STATUSES:
            if f["home_score"] is not None or f["away_score"] is not None:
                non_finished += 1
            f["home_score"] = None
            f["away_score"] = None
    if non_finished:
        print(f"   ⚠️ 已清除 {non_finished} 场未结束比赛的比分（状态非FT/AET/PEN）")

    # Step 2: Enrich with goal scorers from match detail API (if result exists)
    finished_matches = [f for f in fixture_details
                        if f["home_score"] is not None or f["away_score"] is not None]
    if finished_matches:
        print(f"   补充进球数据 ({len(finished_matches)} 场有比分)...")
    for f in finished_matches:
        mid = f.get("id")
        if not mid:
            continue
        try:
            def _fetch_detail():
                resp = requests.get(f"{FOOTBALL_DATA_BASE}/matches/{mid}",
                                   headers=headers, timeout=15)
                resp.raise_for_status()
                return resp.json()
            detail = retry(_fetch_detail, max_retries=1, base_delay=1, desc=f"match-detail({mid})")
            raw_goals = detail.get("match", {}).get("goals", []) or detail.get("goals", [])
            goals = []
            for g in raw_goals:
                scorer = g.get("scorer", {}) or {}
                assist = g.get("assist", {}) or {}
                goals.append({
                    "minute": g.get("minute"),
                    "scorer_name": scorer.get("name", ""),
                    "scorer_team": "home" if g.get("team", {}).get("type", "") == "home" else "away",
                    "assist_name": assist.get("name", ""),
                    "type": g.get("type", "GOAL"),
                })
            if goals:
                f["goals"] = goals
                print(f"   ⚽ {f['home_team']} vs {f['away_team']}: {len(goals)} 粒进球")
            time.sleep(0.6)
        except Exception as e:
            print(f"   ⚠️ match-detail({mid}): {e}")
            time.sleep(0.6)

    # Step 3: Cross-validate World Cup scores against Wikipedia (free, reliable)
    wc_finished = [f for f in fixture_details
                   if f.get("league") == "FIFA World Cup"
                   and (f["home_score"] is not None or f["away_score"] is not None)]
    if wc_finished:
        print(f"   🌐 交叉验证世界比赛分 (Wikipedia)...")
        wiki_scores = _fetch_wikipedia_wc_scores()
        if wiki_scores:
            for f in wc_finished:
                key = (f["home_team"].lower(), f["away_team"].lower())
                wiki_score = wiki_scores.get(key) or wiki_scores.get((key[1], key[0]))
                if wiki_score:
                    wk_h, wk_a = wiki_score
                    if wk_h == f["home_score"] and wk_a == f["away_score"]:
                        f["data_confidence"] = "high"  # 双源一致
                        print(f"   ✅ {f['home_team']} vs {f['away_team']}: {f['home_score']}-{f['away_score']} (Wikipedia一致)")
                    elif wk_h == f["away_score"] and wk_a == f["home_score"]:
                        # 比分一致但主客队对调
                        f["data_confidence"] = "high"
                        print(f"   ✅ {f['home_team']} vs {f['away_team']}: {f['home_score']}-{f['away_score']} (Wikipedia一致, 主客对调)")
                    else:
                        f["data_confidence"] = "conflict"
                        print(f"   ⚠️ {f['home_team']} vs {f['away_team']}: football-data={f['home_score']}-{f['away_score']} vs Wikipedia={wk_h}-{wk_a}")
                else:
                    f["data_confidence"] = "low"  # 单一来源
        else:
            for f in wc_finished:
                f["data_confidence"] = "low"

    by_league = defaultdict(list)
    for f in fixture_details:
        by_league[f["league"]].append(f)
    print(f"   {len(relevant)} 场比赛 ({len(by_league)} 个联赛)")

    standings = fetch_recent_standings()

    result = {"date": date_str, "total_matches": len(relevant),
              "fixtures_by_league": dict(by_league), "all_fixtures": fixture_details, "standings": standings}

    # Log source count
    enriched = sum(1 for f in fixture_details if f.get("goals"))
    high_conf = sum(1 for f in fixture_details if f.get("data_confidence") == "high")
    conflicts = sum(1 for f in fixture_details if f.get("data_confidence") == "conflict")
    if enriched:
        print(f"   📊 数据源: football-data.org (比分{len(finished_matches)}场 + 进球{enriched}场)")
    if high_conf:
        print(f"   📊 双源验证通过: {high_conf}场")
    if conflicts:
        print(f"   ⚠️ 比分冲突(需人工核查): {conflicts}场")
    return result


def _fetch_wikipedia_wc_scores():
    """Fetch 2026 World Cup match results from Wikipedia as cross-validation source.

    Returns dict: {(home_team, away_team): (home_score, away_score)}
    Team names are lowercased for matching. Handles common name variants.
    """
    try:
        resp = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": "2026_FIFA_World_Cup",
                "prop": "extracts",
                "explaintext": 1,
                "format": "json",
            },
            timeout=20,
        )
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        content = ""
        for pid, pdata in pages.items():
            if pid != "-1":
                content = pdata.get("extract", "")
        if not content:
            return None

        # Normalize team name variants for matching
        NAME_MAP = {
            "usa": "united states", "us": "united states",
            "korea republic": "south korea", "south korea": "korea republic",
            "iran": "iran", "côte d'ivoire": "ivory coast",
            "china": "china pr", "saint kitts": "st kitts",
            "saint lucia": "st lucia", "saint vincent": "st vincent",
        }

        def norm(name):
            n = name.lower().strip()
            return NAME_MAP.get(n, n)

        # Find score patterns in Wikipedia text: "Team A 1–2 Team B"
        # Wikipedia uses en-dash (–) for scores
        pattern = r"([A-Za-zÀ-ÿ' ]+?)\s*(\d+)[–-](\d+)\s*([A-Za-zÀ-ÿ' ,]+?)(?:\n|\.|;|\))"
        results = {}
        for m in re.finditer(pattern, content):
            t1_raw = m.group(1).strip()
            s1 = int(m.group(2))
            s2 = int(m.group(3))
            t2_raw = m.group(4).strip()
            t1 = norm(t1_raw)
            t2 = norm(t2_raw.rstrip(".,;)"))
            if s1 >= 0 and s2 >= 0:
                results[(t1, t2)] = (s1, s2)

        if results:
            print(f"   🌐 Wikipedia 解析到 {len(results)} 场比分")
            return results
        return None
    except Exception as e:
        print(f"   ⚠️ Wikipedia API error: {e}")
        return None


# ============================================================
# GZH Trending
# ============================================================

def _is_football_relevant(article):
    """兼容旧函数名：过滤非 NBA 内容。"""
    title = (article.get("title", "") or "") + (article.get("summary", "") or "")
    for pattern in GZH_NOISE_PATTERNS:
        if pattern in title:
            return False
    return True


def get_previously_used_sources(current_date, lookback_days=3):
    used = set()
    today = datetime.strptime(current_date, "%Y-%m-%d")
    for i in range(1, lookback_days + 1):
        dt = today - timedelta(days=i)
        meta_path = OUTPUT_DIR / dt.strftime("%Y-%m-%d") / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
            for a in meta.get("articles", []):
                for src in a.get("sources_used", []):
                    used.add(src[:40])
                if a.get("title"):
                    used.add(a["title"][:40])
        except Exception:
            pass
    if used:
        print(f"   跨天去重: 已加载 {len(used)} 条历史素材/标题")
    return used


def get_topic_history(current_date, lookback_days=7):
    """Track previously covered topics — teams, players, keywords — to avoid repetition."""
    history = {"titles": set(), "keywords": set(), "teams": set(), "players": set(), "content_types": []}
    today = datetime.strptime(current_date, "%Y-%m-%d")
    for i in range(1, lookback_days + 1):
        dt = today - timedelta(days=i)
        meta_path = OUTPUT_DIR / dt.strftime("%Y-%m-%d") / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text())
            for a in meta.get("articles", []):
                title = a.get("title", "")
                if title:
                    history["titles"].add(title[:30])
                # Also track Hupu source post titles for dedup
                source_post = a.get("source_post", "")
                if source_post:
                    history["titles"].add(source_post[:50])
                for kw in a.get("keywords", []):
                    history["keywords"].add(kw.lower())
                for tag in a.get("tags", []):
                    history["keywords"].add(tag.lower())
                for team in WIKI_TEAMS:
                    if team in title:
                        history["teams"].add(team)
                for player in WIKI_PLAYERS:
                    if player in title:
                        history["players"].add(player)
                ct = a.get("content_type", "")
                if ct:
                    history["content_types"].append(ct)
        except Exception:
            pass
    if history["titles"]:
        print(f"   历史去重: 近{lookback_days}天 {len(history['titles'])} 篇, "
              f"覆盖球队 {len(history['teams'])} 支, 球员 {len(history['players'])} 人")
    return history


def fetch_gzh_football_trends(date_str, keyword_groups=None, fallback_match_data=None):
    print(f"[数据] 从公众号爆款库采集NBA话题 ({date_str})...")
    target_date = datetime.strptime(date_str, "%Y-%m-%d")
    start_date = (target_date - timedelta(days=1)).strftime("%Y-%m-%d")
    all_raw = []
    kw_groups = keyword_groups if keyword_groups is not None else GZH_KEYWORD_GROUPS

    gzh_cache = OUTPUT_DIR / "gzh_cache"
    gzh_cache.mkdir(parents=True, exist_ok=True)

    for kw in kw_groups:
        try:
            safe_name = re.sub(r'[^a-zA-Z0-9_一-鿿]', '_', kw)[:30]
            output_file = str(gzh_cache / f"gzh_{safe_name}.json")
            cmd = [sys.executable, GZH_SCRIPT, "--keyword", kw, "--start-date", start_date,
                   "--output-format", "json", "--output-file", output_file]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                if os.path.exists(output_file):
                    data = json.loads(Path(output_file).read_text())
                    for item in data.get("items", []):
                        if _is_football_relevant(item):
                            all_raw.append(item)
                    # Clean up temp file after reading
                    try:
                        Path(output_file).unlink()
                    except OSError:
                        pass
        except Exception as e:
            print(f"   搜索'{kw[:20]}'失败: {e}")

    # Clean up stale cache files (>1 day old)
    try:
        cutoff = time.time() - 86400
        for f in gzh_cache.glob("gzh_*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
    except Exception:
        pass

    if not all_raw:
        print("   公众号爆款库未找到NBA相关文章")
        if fallback_match_data:
            print("   ⚠️ GZH爆款库不可用，尝试从比赛数据构造备选热点...")
            return fetch_fallback_trends(fallback_match_data)
        return []

    seen = set()
    unique = []
    for a in all_raw:
        t = a.get("title", "")[:40]
        if t and t not in seen:
            seen.add(t)
            unique.append(a)
    unique.sort(key=lambda x: x.get("dataScore", 0), reverse=True)

    used_sources = get_previously_used_sources(date_str)
    if used_sources:
        filtered = []
        for a in unique:
            title = a.get("title", "")[:40]
            if title in used_sources:
                continue
            is_dup = any(len(u) >= 10 and (u[:20] in title or title[:20] in u) for u in used_sources)
            if not is_dup:
                filtered.append(a)
        unique = filtered

    if not unique and fallback_match_data:
        print("   ⚠️ GZH爆款库文章全部去重，从比赛数据补充备选热点...")
        return fetch_fallback_trends(fallback_match_data)

    print(f"   采集到 {len(unique)} 篇真实NBA爆款文章")
    for i, a in enumerate(unique[:10]):
        print(f"   {i+1}. [{a.get('clicksCount', '?')}阅读] {a.get('title', '')[:60]} — {a.get('accountName', '?')}")
    return unique


def fetch_fallback_trends(match_data, standings=None):
    """当 GZH 爆款库不可用时，从比赛数据和积分榜构造备选热点话题。

    Returns list of dicts in the same format as GZH articles (title, clicksCount, etc.)
    so the downstream LLM pipeline works identically.
    """
    print("   ⚠️ GZH 爆款库为空，使用比赛数据构造备选热点话题...")
    fallback = []
    idx = 0

    # 1. 从赛果生成高比分、胶着和大胜话题。
    for m in match_data.get("all_fixtures", []):
        hg = m.get("home_score")
        ag = m.get("away_score")
        home = m.get("home_team", "")
        away = m.get("away_team", "")
        league = m.get("league", "")
        if hg is None:
            continue

        total_points = hg + ag
        point_diff = abs(hg - ag)

        if total_points >= 240:
            fallback.append({
                "title": f"对攻大战！{home} {hg}-{ag} {away}，两队合砍{total_points}分",
                "summary": f"这场NBA比赛节奏拉满，两队合计得到{total_points}分。",
                "clicksCount": 50000 + total_points * 100,
                "accountName": "NBA热点",
                "dataScore": 95,
            })
            idx += 1

        if point_diff <= 5 and total_points > 0:
            tag = "加时鏖战" if hg == ag else "险胜"
            fallback.append({
                "title": f"{tag}！{home} {hg}-{ag} {away}，比赛悬念留到最后",
                "summary": f"{home}与{away}的较量直到最后时刻才分出胜负。",
                "clicksCount": 30000 + (6 - point_diff) * 3000,
                "accountName": "NBA热点",
                "dataScore": 90 - point_diff,
            })
            idx += 1

        if point_diff >= 20:
            fallback.append({
                "title": f"一边倒！{home} {hg}-{ag} {away}，分差达到{point_diff}分",
                "summary": f"这场NBA比赛最终分差达到{point_diff}分，胜负早早失去悬念。",
                "clicksCount": 42000 + point_diff * 500,
                "accountName": "NBA热点", "dataScore": min(96, 80 + point_diff // 2),
            })
            idx += 1

    # 2. From standings: top-of-table clashes, relegation battles
    if standings:
        for league_name, table in standings.items():
            if not table:
                continue
            # 分区头名竞争
            if len(table) >= 2:
                top = table[0]
                second = table[1]
                wins_diff = abs((top.get("wins") or 0) - (second.get("wins") or 0))
                if wins_diff <= 2:
                    fallback.append({
                        "title": f"{league_name}头名竞争胶着！{top['team']}与{second['team']}只差{wins_diff}个胜场",
                        "summary": f"{top['team']}和{second['team']}的分区排名竞争仍有悬念。",
                        "clicksCount": 40000 + (3 - wins_diff) * 10000,
                        "accountName": "NBA热点", "dataScore": 90,
                    })
                    idx += 1

            # NBA 没有升降级，不生成“保级”类话题。

    # 3. NBA 比赛日汇总
    nba_matches = [m for m in match_data.get("all_fixtures", []) if m.get("league") == "NBA"]
    if nba_matches:
        groups = set()
        for m in nba_matches:
            groups.add(m.get("matchday", "?"))
        fallback.append({
            "title": f"🏀 NBA赛场日报：今日{len(nba_matches)}场比赛，高光与冷门一次看完",
            "summary": f"今日NBA共有{len(nba_matches)}场比赛，汇总关键比分与真实赛场信息。",
            "clicksCount": 80000 + len(nba_matches) * 5000,
            "accountName": "NBA专区",
            "dataScore": 98,
        })
        idx += 1

        # Check for standout results
        for m in nba_matches[:3]:
            hg = m.get("home_score")
            ag = m.get("away_score")
            if hg is not None and ag is not None and abs(hg - ag) <= 5:
                fallback.append({
                    "title": f"NBA胶着战：{m['home_team']} {hg}-{ag} {m['away_team']}，悬念留到最后",
                    "summary": f"{m['home_team']}与{m['away_team']}打出一场分差不超过5分的胶着比赛。",
                    "clicksCount": 60000,
                    "accountName": "NBA专区",
                    "dataScore": 92,
                })
                idx += 1

    # Deduplicate by title
    seen = set()
    unique = []
    for a in fallback:
        t = a.get("title", "")[:40]
        if t and t not in seen:
            seen.add(t)
            unique.append(a)

    if unique:
        print(f"   ✅ 已从比赛数据构造 {len(unique)} 个备选热点话题")
        for i, a in enumerate(unique[:5]):
            print(f"      {i+1}. [模拟{ a.get('clicksCount', 0)}阅读] {a.get('title', '')[:50]}")
    else:
        print("   ❌ 比赛数据也不足以构造备选话题")
    return unique


def fetch_recent_standings():
    """从虎扑公开榜单页提取 NBA 东西部排名。"""
    standings = {"NBA东部": [], "NBA西部": []}
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(NBA_STANDINGS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        rows = BeautifulSoup(resp.text, "html.parser").select("table tr")
        conference = "NBA东部"
        for row in rows:
            cells = [c.get_text(" ", strip=True) for c in row.select("th,td")]
            if not cells:
                continue
            joined = " ".join(cells)
            if "西部" in joined and not cells[0].isdigit():
                conference = "NBA西部"
                continue
            if not cells[0].isdigit() or len(cells) < 5:
                continue
            standings[conference].append({
                "position": int(cells[0]), "team": cells[1],
                "wins": int(cells[2]) if cells[2].isdigit() else 0,
                "losses": int(cells[3]) if cells[3].isdigit() else 0,
                "win_pct": cells[4], "games_back": cells[5] if len(cells) > 5 else "",
            })
    except Exception as exc:
        print(f"   NBA排名采集失败: {exc}")
    return {k: v for k, v in standings.items() if v}


def fetch_scorers():
    """从虎扑球员榜提取 NBA 场均得分领先者。"""
    leaders = []
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(NBA_PLAYERS_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        for row in BeautifulSoup(resp.text, "html.parser").select("table tr"):
            cells = [c.get_text(" ", strip=True) for c in row.select("th,td")]
            if not cells or not cells[0].isdigit() or len(cells) < 6:
                continue
            leaders.append({"position": int(cells[0]), "player": cells[1], "team": cells[2],
                            "points_per_game": cells[3], "field_goals": cells[4],
                            "field_goal_pct": cells[5]})
            if len(leaders) >= 15:
                break
    except Exception as exc:
        print(f"   NBA球员得分榜采集失败: {exc}")
    return {"NBA": leaders} if leaders else {}


def fetch_rankings_data():
    """汇总 NBA 排名和球员得分榜。"""
    print("[数据] 采集NBA排行榜数据 (排名 + 得分榜)...")
    standings = fetch_recent_standings()
    scorers = fetch_scorers()

    # Build combined rankings context
    rankings = {"standings": {}, "scorers": {}}
    for league, table in standings.items():
        rankings["standings"][league] = table[:10]  # top 10
    for league, top_scorers in scorers.items():
        rankings["scorers"][league] = top_scorers[:10]

    standings_count = len(rankings["standings"])
    scorers_count = len(rankings["scorers"])
    print(f"   分区排名: {standings_count} 组 | 得分榜: {scorers_count} 组")
    return rankings


# ============================================================
# Image Search
# ============================================================

def search_wikipedia(entity_name, lang="en"):
    images = []
    try:
        resp = requests.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(entity_name)}",
            headers={"User-Agent": "WusongShuru/1.0"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if "originalimage" in data:
                images.append({"url": data["originalimage"]["source"], "source": "wikipedia",
                               "alt": data.get("title", entity_name)})
            elif "thumbnail" in data:
                images.append({"url": data["thumbnail"]["source"], "source": "wikipedia",
                               "alt": data.get("title", entity_name)})
    except Exception:
        pass
    return images


def search_footyrenders(keywords, count=5):
    images = []
    search_terms = set()
    for kw in keywords:
        kw_lower = kw.lower()
        for name_key, slug in FOOTYRENDERS_PLAYERS.items():
            if name_key in kw_lower:
                search_terms.add(slug)
    if not search_terms:
        return images
    for term in list(search_terms)[:2]:
        try:
            resp = requests.get(f"https://www.footyrenders.com/?s={requests.utils.quote(term)}",
                              headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            if resp.status_code == 200:
                import re
                pngs = re.findall(r'src="(/cdn/players/[^"]+\.png)"', resp.text)
                for png in pngs:
                    if "1x1-pixel" in png:
                        continue
                    url = f"https://www.footyrenders.com{png}"
                    if url not in [img["url"] for img in images]:
                        images.append({"url": url, "source": "footyrenders", "alt": term.replace("-", " ").title()})
        except Exception:
            pass
    return images[:count]


def extract_search_entities(topic):
    title = topic.get("title", "")
    keywords_cn = topic.get("keywords_cn", [])
    search_text = title + " " + " ".join(keywords_cn)
    players = []
    teams = []
    for cn_name, wiki_page in WIKI_PLAYERS.items():
        if cn_name in search_text:
            players.append({"cn": cn_name, "wiki": wiki_page})
            name_key = cn_name.lower()
            if name_key in FOOTYRENDERS_PLAYERS:
                players[-1]["fr_slug"] = FOOTYRENDERS_PLAYERS[name_key]
    for cn_name, wiki_page in WIKI_TEAMS.items():
        if cn_name in search_text:
            teams.append({"cn": cn_name, "wiki": wiki_page})
    filler = ["的", "了", "是", "在", "和", "也", "都", "就", "要", "会", "能", "不", "这", "那"]
    query_terms = [t.strip() for t in title.replace("？", " ").replace("！", " ").replace("：", " ").split()
                   if len(t.strip()) >= 2 and t.strip() not in filler]
    specific_query = " ".join(query_terms[:5]) if query_terms else title
    return players, teams, specific_query


def search_images(topic, count=5):
    images = []
    keywords = list(topic.get("keywords", [])) if isinstance(topic, dict) else ["business", "technology"]
    en_keywords = [k for k in keywords if isinstance(k, str) and not any('一' <= c <= '鿿' for c in k)]
    players, teams, _ = extract_search_entities(topic) if isinstance(topic, dict) else ([], [], "")

    for p in players[:2]:
        for img in search_wikipedia(p["wiki"]):
            if img["url"] not in [i["url"] for i in images]:
                images.append(img)
    for t in teams[:2]:
        for img in search_wikipedia(t["wiki"]):
            if img["url"] not in [i["url"] for i in images]:
                images.append(img)
    if players:
        for img in search_footyrenders(keywords, count=3):
            if img["url"] not in [i["url"] for i in images]:
                images.append(img)

    if len(images) < count and UNSPLASH_KEY:
        core = " ".join(en_keywords[:4]) if en_keywords else "business technology"
        for q in [core, f"{core} business", "modern business technology"]:
            if len(images) >= count:
                break
            try:
                resp = requests.get("https://api.unsplash.com/search/photos", params={
                    "query": q, "per_page": count - len(images), "orientation": "landscape",
                    "client_id": UNSPLASH_KEY}, timeout=10)
                if resp.status_code == 200:
                    for r in resp.json().get("results", []):
                        images.append({"url": r["urls"]["regular"], "source": "unsplash",
                                       "alt": r.get("description") or q})
            except Exception:
                pass

    if len(images) == 0 and UNSPLASH_KEY:
        try:
            resp = requests.get("https://api.unsplash.com/search/photos", params={
                "query": "business technology", "per_page": count, "orientation": "landscape",
                "client_id": UNSPLASH_KEY}, timeout=10)
            if resp.status_code == 200:
                for r in resp.json().get("results", []):
                    images.append({"url": r["urls"]["regular"], "source": "unsplash", "alt": "business technology"})
        except Exception:
            pass

    # Final fallback: DuckDuckGo (free, no key)
    if len(images) < count:
        try:
            q = " ".join(en_keywords[:3]) if en_keywords else "business technology"
            from urllib.parse import quote_plus as qp
            import re
            ddg = requests.get("https://duckduckgo.com/", params={"q": q}, timeout=10)
            vqd_match = re.search(r'vqd=([\d-]+)', ddg.text)
            if vqd_match:
                vqd = vqd_match.group(1)
                resp = requests.get(
                    f"https://duckduckgo.com/i.js?q={qp(q)}&vqd={vqd}&o=json",
                    timeout=10)
                if resp.status_code == 200:
                    for item in resp.json().get("results", [])[:count]:
                        url = item.get("image", "")
                        if url and url not in [i["url"] for i in images]:
                            images.append({"url": url, "source": "duckduckgo", "alt": item.get("title", "")})
        except Exception:
            pass
    return images[:count]


# ============================================================
# Topic Selection & Article Generation
# ============================================================
