"""财经专用复核：仅检查长文与微头条字数。"""

import re


def validate_article(source_fixture, article):
    """返回 (passed, issues)，只核对字数区间。"""
    issues = []

    article_length = len(re.sub(r"\s+", "", str(article.get("content", ""))))
    micro_length = len(re.sub(r"\s+", "", str(article.get("micro_content", ""))))
    if not 450 <= article_length <= 550:
        issues.append(f"长文章字数{article_length}，应为450—550字")
    if not 220 <= micro_length <= 350:
        issues.append(f"微头条字数{micro_length}，应为220—350字")

    return len(issues) == 0, issues
