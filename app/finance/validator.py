"""财经专用复核：仅检查长文/微头条字数和来源数字。"""

import re


def _extract_normalized_numbers(text):
    cleaned = str(text or "").replace(",", "")
    pattern = re.compile(
        r'(\d+(?:\.\d+)?)\s*'
        r'(万亿|亿元|亿|万元|万|trillion|billion|million|thousand|百分之|percent|%|元)?',
        re.I)
    factors = {
        "万亿": 1e12, "亿元": 1e8, "亿": 1e8, "万元": 1e4, "万": 1e4,
        "trillion": 1e12, "billion": 1e9, "million": 1e6, "thousand": 1e3,
        "百分之": 1.0, "percent": 1.0, "%": 1.0, "元": 1.0, "": 1.0,
    }
    return [
        (match.group(0).strip(), float(match.group(1)) * factors[(match.group(2) or "").lower()])
        for match in pattern.finditer(cleaned)
    ]


def validate_article(source_fixture, article):
    """返回 (passed, issues)，不检查数字与字数之外的任何内容。"""
    source_text = str(source_fixture.get("article_text", ""))
    output_text = "\n".join(str(article.get(key, ""))
                              for key in ("title", "content", "micro_content"))
    issues = []

    article_length = len(re.sub(r"\s+", "", str(article.get("content", ""))))
    micro_length = len(re.sub(r"\s+", "", str(article.get("micro_content", ""))))
    if not 450 <= article_length <= 550:
        issues.append(f"长文章字数{article_length}，应为450—550字")
    if not 220 <= micro_length <= 350:
        issues.append(f"微头条字数{micro_length}，应为220—350字")

    source_numbers = _extract_normalized_numbers(source_text)
    numeric_output = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', output_text)
    numeric_output = re.sub(r'https?://\S+', '', numeric_output)
    for raw, value in _extract_normalized_numbers(numeric_output):
        if not any(abs(value - source_value) <= max(1e-6, abs(source_value) * 1e-9)
                   for _, source_value in source_numbers):
            issues.append(f"新增数字: {raw}")

    return len(issues) == 0, issues
