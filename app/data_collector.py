"""公用采集接口，根据业务标识延迟加载对应采集器。"""

from importlib import import_module

from .constants import CONTENT_APP


def _collector():
    """只加载当前业务采集器，避免两个业务在运行时互相依赖。"""
    return import_module(f"app.{CONTENT_APP}.collector")


def collect_real_matches(date_str, batch_mode="morning"):
    """为保持编排器接口简洁，按业务返回财经新闻或篮球素材。"""
    module = _collector()
    if CONTENT_APP == "basketball":
        return module.collect_basketball_data(date_str)
    return module.collect_finance_news(date_str, batch_mode)


def collect_additional_news(date_str):
    """采集当前业务的补充新闻；不支持时返回空列表。"""
    function = getattr(_collector(), "collect_additional_news", None)
    return function(date_str) if function else []


def collect_future_items(date_str, days_ahead=1):
    """采集当前业务的未来事件；不支持时返回空列表。"""
    function = getattr(_collector(), "collect_future_items", None)
    return function(date_str, days_ahead=days_ahead) if function else []


def collect_rankings():
    """采集当前业务的榜单；不支持时返回空字典。"""
    function = getattr(_collector(), "collect_rankings", None)
    return function() if function else {}


def enrich_source_article(article):
    """按当前业务补全来源正文，并返回正文和结构化附加数据。"""
    function = getattr(_collector(), "enrich_source_article", None)
    if function:
        return function(article)
    return str(article.get("article_text") or ""), {}


__all__ = ["collect_real_matches", "collect_additional_news", "collect_future_items",
           "collect_rankings", "enrich_source_article"]
