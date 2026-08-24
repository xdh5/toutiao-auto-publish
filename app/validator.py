"""财经与篮球公用复核：过去7天标题与正文去重。"""

import json
from datetime import datetime, timedelta
from difflib import SequenceMatcher


def check_cross_day_duplicate(title, content, date_str, output_dir):
    today = datetime.strptime(date_str, "%Y-%m-%d")
    for offset in range(1, 8):
        day = today - timedelta(days=offset)
        meta_path = output_dir / day.strftime("%Y-%m-%d") / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            for article in metadata.get("articles", []):
                old_title = article.get("title", "")
                if not old_title or len(old_title) < 8:
                    continue
                shorter, longer = ((title, old_title) if len(title) <= len(old_title)
                                   else (old_title, title))
                if any(shorter[start:start + 15] in longer
                       for start in range(len(shorter) - 14)):
                    return True, old_title, 100
                title_ratio = SequenceMatcher(None, title[:40], old_title[:40]).ratio()
                if title_ratio > 0.65:
                    return True, old_title, round(title_ratio * 100)
                old_content = article.get("content", "")
                if old_content and len(content) > 50 and len(old_content) > 50:
                    content_ratio = SequenceMatcher(
                        None, content[:100], old_content[:100]).ratio()
                    if content_ratio > 0.7:
                        return True, old_title, round(content_ratio * 100)
        except Exception:
            continue
    return False, "", 0
