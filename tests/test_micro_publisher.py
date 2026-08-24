import json

import pytest

from app import micro_publisher


def _arrange_embedded_micro(tmp_path, monkeypatch, content="同一轮生成的微头条。\n#财经新闻#"):
    date_dir = tmp_path / "2026-08-24"
    date_dir.mkdir(parents=True)
    article_file = date_dir / "article-1-test.md"
    article_file.write_text("# 测试文章", encoding="utf-8")
    (date_dir / "metadata.json").write_text(json.dumps({
        "articles": [{"index": 1, "micro_content": content}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(micro_publisher, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(micro_publisher, "load_articles", lambda *args, **kwargs: [{
        "title": "一家制造企业公布新计划",
        "body": "长文章正文",
        "file": str(article_file),
        "index": "1",
    }])
    return content


def test_generate_micro_reads_same_rewrite_result(tmp_path, monkeypatch):
    expected = _arrange_embedded_micro(tmp_path, monkeypatch)
    draft = micro_publisher.generate_draft("2026-08-24", "noon")
    assert draft["content"] == expected
    assert draft["content_type"] == "新闻微头条"
    assert (tmp_path / "2026-08-24" / "micro-noon.json").exists()


def test_generate_micro_accepts_content_without_length_or_hashtag_gate(tmp_path, monkeypatch):
    expected = _arrange_embedded_micro(tmp_path, monkeypatch, content="短内容也直接使用")
    draft = micro_publisher.generate_draft("2026-08-24", "morning")
    assert draft["content"] == expected


def test_generate_micro_requires_rewrite_to_return_micro_content(tmp_path, monkeypatch):
    _arrange_embedded_micro(tmp_path, monkeypatch, content="")
    with pytest.raises(ValueError, match="没有返回 micro_content"):
        micro_publisher.generate_draft("2026-08-24", "evening")
