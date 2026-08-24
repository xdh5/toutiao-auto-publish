import json

import pytest

import app.orchestrator as orchestrator


@pytest.mark.parametrize("data_source", ["worldnews", "zhibo8"])
def test_rewrite_retries_cross_day_duplicate_for_finance_and_basketball(
        tmp_path, monkeypatch, data_source):
    previous = tmp_path / "2026-08-23"
    previous.mkdir(parents=True)
    (previous / "metadata.json").write_text(json.dumps({
        "articles": [{"title": "这是一条过去已经发布过的相同新闻标题"}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(orchestrator, "OUTPUT_DIR", tmp_path)

    generated = iter([
        {"title": "这是一条过去已经发布过的相同新闻标题", "content": "旧内容" * 200},
        {"title": "今天出现的全新话题不会和旧标题重复", "content": "新内容" * 200},
    ])
    calls = []

    def fake_rewrite(*args, **kwargs):
        calls.append(kwargs.get("retry_hint", ""))
        return next(generated)

    monkeypatch.setattr(orchestrator, "rewrite_article", fake_rewrite)
    source = {"article_text": "来源正文", "fixture": {
        "article_text": "来源正文", "home_team": "", "away_team": "",
        "home_score": None, "away_score": None, "player_stats": [],
    }}
    article, error = orchestrator._rewrite_with_retry(
        {"title": "候选话题", "_word_count_range": [200, 400]},
        {"data_source": data_source}, 1, source, 2, "2026-08-24")

    assert error is None
    assert article["title"] == "今天出现的全新话题不会和旧标题重复"
    assert len(calls) == 2
    assert "过去7天" in calls[1]


def test_cross_day_duplicate_checks_saved_content_prefix(tmp_path, monkeypatch):
    previous = tmp_path / "2026-08-23"
    previous.mkdir(parents=True)
    shared = "企业公布全新计划，市场正在关注后续变化。" * 8
    (previous / "metadata.json").write_text(json.dumps({
        "articles": [{"title": "完全不同的旧标题示例", "content": shared}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(orchestrator, "OUTPUT_DIR", tmp_path)

    duplicated, matched, score = orchestrator.check_cross_day_duplicate(
        "今天另一条完全不同的新标题", shared, "2026-08-24")

    assert duplicated is True
    assert matched == "完全不同的旧标题示例"
    assert score > 70
