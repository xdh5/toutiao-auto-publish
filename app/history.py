"""财经与篮球共用的跨批次、跨日期去重记录读取。"""

import json
from datetime import datetime, timedelta

from .constants import OUTPUT_DIR, WIKI_PLAYERS, WIKI_TEAMS


def get_previously_used_sources(current_date, lookback_days=3):
    """返回近期已发布文章的来源标题和文章标题。"""
    used = set()
    today = datetime.strptime(current_date, "%Y-%m-%d")
    for offset in range(1, lookback_days + 1):
        meta_path = OUTPUT_DIR / (today - timedelta(days=offset)).strftime("%Y-%m-%d") / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            for article in metadata.get("articles", []):
                used.update(str(source)[:40] for source in article.get("sources_used", []))
                if article.get("title"):
                    used.add(str(article["title"])[:40])
        except (OSError, ValueError, TypeError):
            continue
    if used:
        print(f"   跨天去重: 已加载 {len(used)} 条历史素材/标题")
    return used


def get_topic_history(current_date, lookback_days=7):
    """读取近期已覆盖的标题、关键词、球队、球员和内容类型。"""
    history = {"titles": set(), "keywords": set(), "teams": set(),
               "players": set(), "content_types": []}
    today = datetime.strptime(current_date, "%Y-%m-%d")
    for offset in range(1, lookback_days + 1):
        meta_path = OUTPUT_DIR / (today - timedelta(days=offset)).strftime("%Y-%m-%d") / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            for article in metadata.get("articles", []):
                title = str(article.get("title") or "")
                if title:
                    history["titles"].add(title[:30])
                source_post = str(article.get("source_post") or "")
                if source_post:
                    history["titles"].add(source_post[:50])
                for keyword in list(article.get("keywords", [])) + list(article.get("tags", [])):
                    if isinstance(keyword, str):
                        history["keywords"].add(keyword.lower())
                history["teams"].update(team for team in WIKI_TEAMS if team in title)
                history["players"].update(player for player in WIKI_PLAYERS if player in title)
                if article.get("content_type"):
                    history["content_types"].append(article["content_type"])
        except (OSError, ValueError, TypeError):
            continue
    if history["titles"]:
        print(f"   历史去重: 近{lookback_days}天 {len(history['titles'])} 篇, "
              f"覆盖球队 {len(history['teams'])} 支, 球员 {len(history['players'])} 人")
    return history
