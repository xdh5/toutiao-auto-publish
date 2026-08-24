"""验证财经和篮球两阶段 Prompt 均存在且被运行时代码调用。"""

import inspect
import json
import hashlib
from pathlib import Path

import pytest

import app.orchestrator as orchestrator
from app.utils import load_prompt_template


PROMPT_DIR = Path(__file__).parent.parent / "prompts"
PROMPT_FILES = ("topic_selector.txt", "rewrite_article.txt")
EXPECTED_PROMPT_HASHES = {
    "basketball/rewrite_article.txt": "09b211d87a8448df86cf416106a04e2cd6adab458493ece1c03022dd4c6add41",
    "basketball/topic_selector.txt": "904a61930ada5b9eede2a9adec7bed6796e020b3df696b0e4bba51e886817474",
    "finance/rewrite_article.txt": "080d846f94014d437f1fbc369083474ce943ebf925909c0ec4cceb1b02eadb06",
    "finance/topic_selector.txt": "c5dcbae1a15f1156512a98f9c8c09c38eefa15d7d9415d7a17e2c2c34fac08c6",
}


@pytest.mark.parametrize("content_app", ["finance", "basketball"])
@pytest.mark.parametrize("filename", PROMPT_FILES)
def test_business_prompt_files_exist(content_app, filename):
    path = PROMPT_DIR / content_app / filename
    assert path.exists(), f"缺少 {path}"
    assert path.stat().st_size > 500, f"Prompt 内容过短: {path}"
    assert load_prompt_template(filename, content_app)


def test_runtime_calls_selection_and_direct_rewrite():
    selection_source = inspect.getsource(orchestrator.select_topics)
    rewrite_sources = (
        inspect.getsource(orchestrator._rewrite_finance_article)
        + inspect.getsource(orchestrator.rewrite_article)
    )
    pipeline_source = inspect.getsource(orchestrator._rewrite_with_retry)
    assert 'load_prompt_template("topic_selector.txt")' in selection_source
    assert 'load_prompt_template("rewrite_article.txt")' in rewrite_sources
    assert "generate_article_draft" not in pipeline_source
    assert "rewrite_article(" in pipeline_source


def test_prompts_match_locked_reference_variants():
    for relative_path, expected in EXPECTED_PROMPT_HASHES.items():
        text = (PROMPT_DIR / relative_path).read_text(encoding="utf-8").replace("\r\n", "\n")
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == expected


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


def test_finance_prompts_keep_finance_scope_and_source_facts():
    selector = load_prompt_template("topic_selector.txt", "finance")
    rewrite = load_prompt_template("rewrite_article.txt", "finance")
    assert "财经" in selector
    assert "来源文章" in rewrite


def test_basketball_prompts_keep_basketball_scope_and_fidelity():
    prompts = [load_prompt_template(name, "basketball") for name in PROMPT_FILES]
    assert all("篮球" in prompt for prompt in prompts)
    assert all("岛哥侃篮球" in prompt for prompt in prompts)
    assert all("球评人老六" not in prompt for prompt in prompts)
    assert "事实零改动" in prompts[1]
