#!/usr/bin/env python3
"""NBA 数据源健康检测。

检查直播吧 NBA 频道的可访问性、新闻列表和正文解析。NBA 无比赛日（尤其
休赛期）属于正常情况，不会因为赛程为空而阻断文章生成。
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from bs4 import BeautifulSoup

from media_scraper import SportsScraper


def check_zhibo8(scraper, do_save_html=False, save_dir=None):
    """返回 ``(status, checks, errors)``。"""
    checks = {}
    errors = []

    try:
        html = scraper._http_get(f"{scraper.ZHIBO8_BASE}/", check_block=True)
    except Exception as exc:
        checks["accessible"] = False
        return "broken", checks, [f"直播吧不可达: {exc}"]

    checks["accessible"] = "直播吧" in html or "zhibo8" in html.lower()
    if not checks["accessible"]:
        errors.append("直播吧首页内容异常")

    soup = BeautifulSoup(html, "html.parser")
    basketball_items = soup.select("li[data-type='basketball']")
    nba_items = []
    for item in basketball_items:
        league_el = item.select_one("._league")
        league = league_el.get_text(" ", strip=True) if league_el else ""
        if league.upper() == "NBA":
            nba_items.append(item)

    checks["basketball_items_count"] = len(basketball_items)
    checks["nba_items_count"] = len(nba_items)
    checks["schedule_note"] = "无赛程可为NBA休赛期正常状态" if not nba_items else "检测到NBA赛程"

    today = datetime.now().strftime("%Y-%m-%d")
    parsed = scraper._parse_zhibo8_homepage(html, today)
    checks["parsed_nba_matches"] = len(parsed)

    try:
        news = scraper.scrape_basketball_news(date_str=today, max_articles=5)
        checks["news_articles_found"] = len(news)
        checks["sample_title"] = news[0].get("title", "")[:60] if news else ""
        content = scraper.scrape_zhibo8_article_content(news[0]["url"]) if news else ""
        checks["news_content_ok"] = bool(content and len(content) > 100)
        if len(news) < 3:
            errors.append(f"今日NBA新闻不足3篇（当前{len(news)}篇）")
        if news and not checks["news_content_ok"]:
            errors.append("NBA新闻正文解析失败")
    except Exception as exc:
        checks["news_articles_found"] = 0
        checks["news_content_ok"] = False
        errors.append(f"NBA新闻频道异常: {exc}")

    if do_save_html and save_dir:
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        snapshot = save_dir / f"zhibo8_nba_{datetime.now():%H%M%S}.html"
        snapshot.write_text(html, encoding="utf-8")
        checks["html_snapshot"] = str(snapshot)

    if not checks["accessible"] or checks.get("news_articles_found", 0) == 0:
        status = "broken"
    elif checks.get("news_articles_found", 0) < 3 or not checks.get("news_content_ok", False):
        status = "degraded"
    else:
        status = "healthy"
    return status, checks, errors


def format_text(report):
    emoji = {"healthy": "✅", "degraded": "⚠️", "broken": "❌"}
    source = report["sources"]["zhibo8_nba"]
    lines = [
        "",
        "=" * 55,
        f"  NBA数据源健康检测 — {report['timestamp']}",
        f"  整体状态: {emoji.get(report['overall'], '?')} {report['overall']}",
        f"  建议: {report['recommendation']}",
        "=" * 55,
    ]
    for key, value in source["checks"].items():
        if isinstance(value, bool):
            value = "✅" if value else "❌"
        lines.append(f"  {key}: {value}")
    lines.extend(f"  🚨 {error}" for error in source["errors"])
    return "\n".join(lines)


def send_alert(report):
    try:
        import requests
        from constants import WXPUSHER_APPTOKEN, WXPUSHER_UID

        source = report["sources"]["zhibo8_nba"]
        details = "; ".join(source["errors"][:3]) or "NBA数据源状态降级"
        requests.post(
            "https://wxpusher.zjiecode.com/api/send/message",
            json={
                "appToken": WXPUSHER_APPTOKEN,
                "content": f"⚠️ NBA数据源告警\n\n{details[:500]}",
                "contentType": 1,
                "uids": [WXPUSHER_UID],
            },
            timeout=10,
        )
    except Exception as exc:
        print(f"⚠️ WxPusher通知失败: {exc}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="NBA数据源健康检测")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--output")
    parser.add_argument("--alert", action="store_true")
    parser.add_argument("--save-html")
    args = parser.parse_args()

    status, checks, errors = check_zhibo8(
        SportsScraper(), bool(args.save_html), Path(args.save_html) if args.save_html else None
    )
    report = {
        "timestamp": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "overall": status,
        "recommendation": "proceed" if status == "healthy" else "fallback_news" if status == "degraded" else "abort",
        "sources": {"zhibo8_nba": {"status": status, "checks": checks, "errors": errors}},
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) if args.format == "json" else format_text(report)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"报告已写入: {args.output}", file=sys.stderr if args.format == "json" else sys.stdout)
    else:
        print(output)

    if args.alert and status != "healthy":
        send_alert(report)
    raise SystemExit(0 if status == "healthy" else 1 if status == "degraded" else 2)


if __name__ == "__main__":
    main()
