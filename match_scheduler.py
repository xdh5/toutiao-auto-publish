#!/usr/bin/env python3
"""NBA 赛程预取、焦点战标记与内容序列规划。"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from media_scraper import SportsScraper

PROJECT_ROOT = Path(__file__).parent

BIG_TEAMS = {
    "湖人", "勇士", "凯尔特人", "尼克斯", "快船", "太阳", "雄鹿", "独行侠",
    "掘金", "雷霆", "热火", "76人", "火箭", "马刺",
    "Lakers", "Warriors", "Celtics", "Knicks", "Clippers", "Suns", "Bucks",
    "Mavericks", "Nuggets", "Thunder", "Heat", "76ers", "Rockets", "Spurs",
}


def _is_focus_match(match):
    teams = f"{match.get('home_team', '')} {match.get('away_team', '')}".lower()
    return any(team.lower() in teams for team in BIG_TEAMS)


def fetch_upcoming_matches(days_ahead=3):
    """从直播吧预取今天起若干天的 NBA 赛程。"""
    cst = ZoneInfo("Asia/Shanghai")
    today = datetime.now(cst).date()
    scraper = SportsScraper()
    matches = []
    seen = set()

    print(f"📅 NBA赛事日历: 查询 {today} ~ {today + timedelta(days=days_ahead)}")
    for offset in range(days_ahead + 1):
        date_str = (today + timedelta(days=offset)).isoformat()
        day_matches = scraper.scrape_zhibo8_schedule(date_str)
        for match in day_matches:
            key = (match.get("match_url"), match.get("home_team"), match.get("away_team"))
            if key in seen:
                continue
            seen.add(key)
            match = dict(match)
            match["league"] = "NBA"
            match["cst_date"] = date_str
            match["cst_time"] = match.get("utc_date", "")
            match["focus_match"] = _is_focus_match(match)
            matches.append(match)

    matches.sort(key=lambda item: (item.get("cst_date", ""), item.get("cst_time", "")))
    focus_count = sum(bool(item["focus_match"]) for item in matches)
    print(f"   📊 共 {len(matches)} 场NBA比赛，{focus_count} 场焦点战")
    return matches


def plan_content_sequence(matches):
    """为 NBA 焦点战生成前瞻、复盘和数据深读建议。"""
    plans = []
    for match in matches:
        if not match.get("focus_match"):
            continue
        date_str = match.get("cst_date") or match.get("match_date")
        if not date_str:
            continue
        match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        home, away = match["home_team"], match["away_team"]
        label = f"{home} vs {away}"
        plans.extend([
            {
                "date": match_date.isoformat(), "match": label, "league": "NBA",
                "content_type": "preview", "suggested_batch": "morning",
                "label": f"🔮 赛前前瞻：{label}",
                "rationale": "分析阵容状态、攻防对位和比赛看点",
            },
            {
                "date": (match_date + timedelta(days=1)).isoformat(), "match": label, "league": "NBA",
                "content_type": "review", "suggested_batch": "evening",
                "label": f"📺 赛后复盘：{label}",
                "rationale": "复盘关键回合、球星表现和教练调整",
            },
            {
                "date": (match_date + timedelta(days=2)).isoformat(), "match": label, "league": "NBA",
                "content_type": "deep_dive", "suggested_batch": "noon",
                "label": f"📊 数据深读：{label}",
                "rationale": "从效率、篮板、失误和正负值拆解胜负手",
            },
        ])
    print(f"📋 NBA内容序列规划：{len(plans)} 条建议")
    return plans


def save_schedule(matches, plans, output_dir=None):
    output_dir = Path(output_dir) if output_dir else PROJECT_ROOT / "output" / "schedule"
    output_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M"),
        "league": "NBA",
        "matches": matches,
        "content_plans": plans,
    }
    filepath = output_dir / "match_schedule.json"
    filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 NBA赛事日历已保存: {filepath}")
    return filepath


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    upcoming = fetch_upcoming_matches(days)
    save_schedule(upcoming, plan_content_sequence(upcoming))
