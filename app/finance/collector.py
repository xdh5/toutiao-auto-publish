"""财经专用新闻采集。"""

import re
from urllib.parse import urlparse

import requests

from ..constants import WORLD_NEWS_API_KEY, WORLD_NEWS_URL


def collect_finance_news(date_str, batch_mode):
    """按批次采集国内或海外财经科技新闻。"""
    if not WORLD_NEWS_API_KEY:
        raise RuntimeError("缺少 WORLD_NEWS_API_KEY")
    region = "overseas" if batch_mode == "noon" else "cn"
    params = {"categories": "business,technology", "number": 10, "sort": "publish-time"}
    if region == "cn":
        params.update({"source-countries": "cn", "language": "zh"})
    else:
        params.update({"source-countries": "us,gb,ca,au", "language": "en"})
    response = requests.get(
        WORLD_NEWS_URL, headers={"x-api-key": WORLD_NEWS_API_KEY},
        params=params, timeout=30)
    response.raise_for_status()
    rows = response.json().get("news") or []
    overseas_terms = (
        "china", "chinese", "ai", "semiconductor", "chip", "electric vehicle",
        "automaker", "consumer", "retail", "manufacturing", "supply chain", "factory",
        "apple", "tesla", "nvidia", "microsoft", "google", "amazon", "meta", "tiktok",
    )
    articles = []
    for raw in rows:
        title = str(raw.get("title") or "").strip()
        text = str(raw.get("text") or "").strip()
        url = str(raw.get("url") or "").strip()
        category = str(raw.get("category") or "").lower()
        host = re.sub(r"^www\.", "", urlparse(url).hostname or "").lower()
        combined = f" {title} {text} {host} ".lower()
        if not title or not text or not url or category not in ("business", "technology"):
            continue
        if region == "overseas" and not any(term in combined for term in overseas_terms):
            continue
        articles.append({
            "article_id": str(raw.get("id") or url), "title": title, "url": url,
            "article_text": text, "source": host, "source_images": [],
            "category": category, "region": region,
            "_content_type_hint": "科技动态" if category == "technology" else (
                "海外商业" if region == "overseas" else "国内商业"),
        })
    print(f"[1/5] 采集财经新闻 ({date_str}, {region})：通过 {len(articles)}/{len(rows)} 条")
    return _finance_result(date_str, batch_mode, "worldnews", articles)


def _finance_result(date_str, batch_mode, source, articles):
    return {
        "date": date_str, "total_matches": 0, "fixtures_by_league": {},
        "all_fixtures": [], "standings": {}, "data_source": source,
        "batch_mode": batch_mode, "media_reports": {},
        "news_articles": articles, "transfer_news": [],
    }
