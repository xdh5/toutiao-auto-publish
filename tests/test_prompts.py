"""验证财经和篮球三阶段 Prompt 均存在且被运行时代码调用。"""

import inspect
import json
from pathlib import Path

import pytest

import app.orchestrator as orchestrator
from app.utils import load_prompt_template


PROMPT_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_FILES = ("topic_selector.txt", "article_generator.txt", "rewrite_article.txt")


@pytest.mark.parametrize("content_app", ["finance", "basketball"])
@pytest.mark.parametrize("filename", PROMPT_FILES)
def test_business_prompt_files_exist(content_app, filename):
    path = PROMPT_DIR / content_app / filename
    assert path.exists(), f"缺少 {path}"
    assert path.stat().st_size > 500, f"Prompt 内容过短: {path}"
    assert load_prompt_template(filename, content_app)


def test_runtime_calls_all_three_prompt_stages():
    selection_source = inspect.getsource(orchestrator.select_topics)
    draft_source = inspect.getsource(orchestrator.generate_article_draft)
    rewrite_sources = (
        inspect.getsource(orchestrator._rewrite_finance_article)
        + inspect.getsource(orchestrator.rewrite_article)
    )
    assert 'load_prompt_template("topic_selector.txt")' in selection_source
    assert 'load_prompt_template("article_generator.txt")' in draft_source
    assert 'load_prompt_template("rewrite_article.txt")' in rewrite_sources


def test_pipeline_orders_draft_before_rewrite():
    source = inspect.getsource(orchestrator._rewrite_with_retry)
    assert source.index("generate_article_draft(") < source.index("rewrite_article(")


def test_finance_selector_uses_ai_selected_article_id(monkeypatch):
    rows = [
        {"article_id": "first", "title": "第一条", "article_text": "甲" * 150,
         "url": "https://example.com/1", "source": "example.com",
         "category": "business", "region": "cn"},
        {"article_id": "second", "title": "第二条", "article_text": "乙" * 150,
         "url": "https://example.com/2", "source": "example.com",
         "category": "technology", "region": "cn"},
    ]
    response = [{"article_id": "second", "title": "第二条", "angle": "产业影响",
                 "keywords": ["technology"], "keywords_cn": ["科技"]}]
    monkeypatch.setattr(orchestrator, "call_llm", lambda *_args, **_kwargs: json.dumps(response, ensure_ascii=False))
    topics = orchestrator.select_topics({
        "data_source": "worldnews", "date": "2026-08-24", "batch_mode": "morning",
        "news_articles": rows,
    }, topic_count=1)
    assert topics[0]["_source_article_id"] == "second"
    assert topics[0]["angle"] == "产业影响"


def test_article_generator_template_is_used_for_draft(monkeypatch):
    loaded = []
    original_loader = orchestrator.load_prompt_template

    def recording_loader(name):
        loaded.append(name)
        return original_loader(name, "finance")

    monkeypatch.setattr(orchestrator, "load_prompt_template", recording_loader)
    monkeypatch.setattr(orchestrator, "CONTENT_APP", "finance")
    monkeypatch.setattr(orchestrator, "call_llm", lambda *_args, **_kwargs: json.dumps({
        "title": "财经初稿标题", "content": "中" * 500,
    }, ensure_ascii=False))
    draft = orchestrator.generate_article_draft(
        {"title": "来源标题", "angle": "行业影响", "content_type": "国内商业"},
        {"article_text": "来源正文" * 100, "fixture": {"article_title": "来源标题"}},
        1,
    )
    assert draft["title"] == "财经初稿标题"
    assert loaded == ["article_generator.txt"]


def test_finance_prompts_exclude_politics_and_keep_source_facts():
    selector = load_prompt_template("topic_selector.txt", "finance")
    generator = load_prompt_template("article_generator.txt", "finance")
    rewrite = load_prompt_template("rewrite_article.txt", "finance")
    assert "排除政治" in selector
    assert all("来源" in prompt for prompt in (generator, rewrite))


def test_basketball_prompts_keep_nba_scope_and_fidelity():
    prompts = [load_prompt_template(name, "basketball") for name in PROMPT_FILES]
    assert all("NBA" in prompt for prompt in prompts)
    assert "事实零改动" in prompts[2]
