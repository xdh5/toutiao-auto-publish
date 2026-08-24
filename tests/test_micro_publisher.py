import json

import pytest

import micro_publisher


def _valid_content():
    paragraph = "中年以后我才明白，真正让人安心的不是一句漂亮承诺，而是每天认真工作、按时存下一点钱，也愿意照顾好身边的人。"
    return "\n\n".join([paragraph, paragraph, paragraph, paragraph, paragraph]) + "\n\n#中年生活#"


def test_validate_micro_content_accepts_valid_length_and_source_numbers():
    content = _valid_content()
    micro_publisher._validate_content(content, content)


def test_validate_micro_content_rejects_invented_number():
    content = _valid_content().replace("\n\n#中年生活#", "后来我又多赚了99元。\n\n#中年生活#")
    with pytest.raises(ValueError, match="新增了原文没有的数字"):
        micro_publisher._validate_content(content, _valid_content())


def test_validate_micro_content_requires_hashtag():
    content = _valid_content().replace("\n\n#中年生活#", "")
    with pytest.raises(ValueError, match="话题标签"):
        micro_publisher._validate_content(content, content)


def test_generate_noon_micro_uses_news_article(tmp_path, monkeypatch):
    content = _valid_content()
    monkeypatch.setattr(micro_publisher, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        micro_publisher,
        "load_articles",
        lambda *args, **kwargs: [{
            "title": "一家制造企业公布新计划",
            "body": content,
            "file": "article.md",
        }],
    )
    result = {"content": content}
    monkeypatch.setattr(
        micro_publisher,
        "call_llm",
        lambda *args, **kwargs: json.dumps(result, ensure_ascii=False),
    )

    draft = micro_publisher.generate_draft("2026-08-24", "noon")

    assert draft["content_type"] == "新闻微头条"
    assert draft["topic"] == "一家制造企业公布新计划"
    assert (tmp_path / "2026-08-24" / "micro-noon.json").exists()


def test_generate_morning_micro_uses_article_content_type(tmp_path, monkeypatch):
    content = _valid_content()
    monkeypatch.setattr(micro_publisher, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        micro_publisher,
        "load_articles",
        lambda *args, **kwargs: [{
            "title": "国内企业公布新计划",
            "body": content,
            "file": "article.md",
            "meta": {"content_type": "国内商业"},
        }],
    )
    monkeypatch.setattr(
        micro_publisher,
        "call_llm",
        lambda *args, **kwargs: json.dumps({"content": content}, ensure_ascii=False),
    )

    draft = micro_publisher.generate_draft("2026-08-25", "morning")

    assert draft["content_type"] == "新闻微头条"


def test_generate_micro_retries_when_first_draft_is_too_short(tmp_path, monkeypatch):
    valid = _valid_content()
    responses = iter([
        json.dumps({"content": "太短了。\n\n#财经新闻#"}, ensure_ascii=False),
        json.dumps({"content": valid}, ensure_ascii=False),
    ])
    calls = []
    monkeypatch.setattr(micro_publisher, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        micro_publisher,
        "load_articles",
        lambda *args, **kwargs: [{
            "title": "国内企业公布新计划",
            "body": valid,
            "file": "article.md",
            "meta": {"content_type": "国内商业"},
        }],
    )

    def fake_llm(*args, **kwargs):
        calls.append(args)
        return next(responses)

    monkeypatch.setattr(micro_publisher, "call_llm", fake_llm)

    draft = micro_publisher.generate_draft("2026-08-25", "morning")

    assert draft["content"] == valid
    assert len(calls) == 2
