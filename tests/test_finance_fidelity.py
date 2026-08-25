import inspect

import app.orchestrator as orchestrator
from app.finance.validator import validate_article


def _article(content="中" * 500, micro_content="短" * 250, **extra):
    return {"title": "财经新闻标题", "content": content,
            "micro_content": micro_content, **extra}


def test_finance_program_review_is_in_rewrite_pipeline():
    source = inspect.getsource(orchestrator._rewrite_with_retry)
    assert "from .finance.validator import validate_article" in source


def test_finance_fidelity_accepts_target_lengths():
    fixture = {"article_text": "公司公布了新的经营计划。"}
    article = _article(
        content="公司公布了新的经营计划。" + "中" * 488,
        micro_content="公司公布了新的经营计划。" + "短" * 230,
    )
    passed, issues = validate_article(fixture, article)
    assert passed is True
    assert issues == []


def test_finance_fidelity_allows_numbers_not_in_source():
    fixture = {"article_text": "公司公布了新的经营计划。"}
    article = _article(content="公司预计投入99亿元。" + "中" * 488)
    passed, issues = validate_article(fixture, article)
    assert passed is True
    assert issues == []


def test_finance_fidelity_checks_article_and_micro_lengths():
    fixture = {"article_text": "公司公布经营计划。"}
    passed, issues = validate_article(
        fixture, _article(content="中" * 449, micro_content="短" * 351))
    assert passed is False
    assert any("长文章字数449" in issue for issue in issues)
    assert any("微头条字数351" in issue for issue in issues)
