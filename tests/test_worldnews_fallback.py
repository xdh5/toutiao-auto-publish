import json

import pytest

import app.orchestrator as orchestrator


def _row(article_id, title):
    return {
        "article_id": article_id,
        "title": title,
        "article_text": "这是一段足够长的来源正文。" * 20,
        "url": f"https://example.com/{article_id}",
        "source": "example.com",
        "_content_type_hint": "海外商业",
    }


def test_worldnews_http_400_skips_to_next_article(monkeypatch):
    first = _row("first", "第一篇触发审核")
    second = _row("second", "第二篇正常生成")
    context = {"data_source": "worldnews", "news_articles": [first, second]}
    topic = {"title": first["title"], "content_type": "海外商业", "_source_article_id": "first"}
    calls = []

    def fake_rewrite(candidate_topic, match_context, index, source, max_retries, date_str):
        calls.append(candidate_topic["_source_article_id"])
        if candidate_topic["_source_article_id"] == "first":
            return {}, "LLM HTTP 400: 400 Client Error"
        return {"title": candidate_topic["title"], "content": "生成成功"}, None

    monkeypatch.setattr(orchestrator, "_rewrite_with_retry", fake_rewrite)
    article, error = orchestrator.generate_article_with_retry(topic, context, 1)

    assert error is None
    assert article["title"] == second["title"]
    assert topic["title"] == second["title"]
    assert topic["_source_article_id"] == "second"
    assert calls == ["first", "second"]


def test_worldnews_non_400_failure_switches_source(monkeypatch):
    first = _row("first", "第一篇")
    second = _row("second", "第二篇")
    context = {"data_source": "worldnews", "news_articles": [first, second]}
    topic = {"title": first["title"], "content_type": "海外商业", "_source_article_id": "first"}
    calls = []

    def fake_rewrite(candidate_topic, match_context, index, source, max_retries, date_str):
        calls.append(candidate_topic["_source_article_id"])
        if candidate_topic["_source_article_id"] == "first":
            return {}, "正文为248字，应为450—550字"
        return {"title": candidate_topic["title"], "content": "中" * 500}, None

    monkeypatch.setattr(orchestrator, "_rewrite_with_retry", fake_rewrite)
    article, error = orchestrator.generate_article_with_retry(topic, context, 1)

    assert error is None
    assert article["title"] == second["title"]
    assert calls == ["first", "second"]


def test_finance_article_translates_and_enforces_chinese_length(monkeypatch):
    content = "中" * 500
    responses = iter([
        json.dumps({"article": {
            "title": "金价上涨背后的市场变化",
            "backup_title": "黄金市场出现新变化",
            "content": content,
            "summary": "市场消息",
            "keywords": ["gold market"],
        }}, ensure_ascii=False),
        json.dumps({
            "passed": True,
            "facts_ok": True,
            "source_ok": True,
            "title_ok": True,
            "issues": [],
        }, ensure_ascii=False),
    ])
    monkeypatch.setattr(orchestrator, "call_llm", lambda *args, **kwargs: next(responses))
    topic = {"title": "Gold market update", "content_type": "海外商业"}
    source = {
        "article_text": "Gold prices rose while other precious metals were stable. " * 8,
        "fixture": {
            "source": "worldnews",
            "article_title": "Gold market update",
            "source_name": "example.com",
            "source_url": "https://example.com/gold",
        },
    }

    article = orchestrator._rewrite_finance_article(topic, source, {"title": "初稿", "content": "中" * 500})

    assert article["title"] == "金价上涨背后的市场变化"
    assert len(article["content"]) == 500
    assert article["source_verbatim"] is False


def test_finance_article_rejects_body_outside_target_length(monkeypatch):
    result = {"article": {
        "title": "中文新闻标题",
        "backup_title": "中文备选标题",
        "content": "中" * 449,
        "keywords": ["business"],
    }}
    monkeypatch.setattr(
        orchestrator,
        "call_llm",
        lambda *args, **kwargs: json.dumps(result, ensure_ascii=False),
    )

    with pytest.raises(ValueError, match="450—550"):
        orchestrator._rewrite_finance_article(
            {"title": "Business update", "content_type": "海外商业"},
            {"article_text": "English source " * 30, "fixture": {"source": "worldnews"}},
            {"title": "初稿", "content": "中" * 500},
        )
