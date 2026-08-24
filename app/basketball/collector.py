#!/usr/bin/env python3
"""篮球专用数据采集模块。

负责 NBA 比赛、新闻、交易、排名和图片素材采集。
"""

import requests
from datetime import datetime, timedelta
from collections import defaultdict

from ..constants import NBA_STANDINGS_URL, NBA_PLAYERS_URL


# ============================================================
# Data Collection
# ============================================================


def collect_basketball_data(date_str):
    """采集指定日期 NBA 比赛、战报与新闻。"""
    print(f"[1/5] 采集 NBA 比赛与新闻 ({date_str})...")
    from .media_scraper import SportsScraper

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
    from .media_scraper import SportsScraper
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


def collect_additional_news(date_str):
    """实现公用采集接口：返回 NBA 交易和签约新闻。"""
    return collect_transfer_news(date_str)


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

    from .media_scraper import SportsScraper
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


def collect_future_items(date_str, days_ahead=1):
    """实现公用采集接口：返回未来 NBA 赛程。"""
    return collect_future_matches(date_str, days_ahead=days_ahead)


def enrich_source_article(article):
    """实现公用采集接口：补抓直播吧正文和球员数据。"""
    from .media_scraper import SportsScraper

    article_text = str(article.get("article_text") or "")
    if len(article_text) < 100:
        try:
            article_text = SportsScraper().scrape_zhibo8_article_content(article.get("url", ""))
        except Exception:
            article_text = ""
    details = {"player_stats": SportsScraper._extract_player_stats_from_text(article_text)} \
        if article_text else {}
    return article_text, details


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


def fetch_fallback_trends(match_data, standings=None):
    """从比赛数据和积分榜构造备选热点话题。"""
    print("   ⚠️ 新闻素材不足，使用比赛数据构造备选热点话题...")
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


def collect_rankings():
    """实现公用采集接口：返回 NBA 排名和得分榜。"""
    return fetch_rankings_data()


