#!/usr/bin/env python3
"""Unit tests for intra-batch dedup in select_topics."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_dedup_no_overlap():
    """Two topics with completely different keywords should pass."""
    from app.orchestrator import _check_intra_batch_dedup

    topics = [
        {"title": "湖人险胜勇士", "keywords": ["Lakers", "Warriors", "NBA"],
         "keywords_cn": ["湖人", "勇士"], "score": 90},
        {"title": "某车企发布新车型", "keywords": ["EV", "China", "Business"],
         "keywords_cn": ["汽车", "制造业"], "score": 85},
    ]
    clean, warnings = _check_intra_batch_dedup(topics)
    assert len(warnings) == 0, f"Expected 0 warnings, got {len(warnings)}: {warnings}"
    assert len(clean) == 2
    print("  PASS test_dedup_no_overlap")


def test_dedup_high_overlap_warns():
    """Two topics sharing >40% keywords should trigger warning."""
    from app.orchestrator import _check_intra_batch_dedup

    topics = [
        {"title": "库里带领勇士取胜", "keywords": ["Curry", "Warriors", "NBA"],
         "keywords_cn": ["库里", "勇士"], "score": 90},
        {"title": "库里的勇士生涯新纪录", "keywords": ["Curry", "NBA", "Record"],
         "keywords_cn": ["库里", "纪录"], "score": 85},
    ]
    clean, warnings = _check_intra_batch_dedup(topics)
    # Curry + NBA overlap = 2/3 = 66% > 40% → warning
    assert len(warnings) >= 1, f"Expected >=1 warning for 66% overlap, got {len(warnings)}"
    print("  PASS test_dedup_high_overlap_warns")


def test_dedup_single_topic_no_warning():
    """Single topic should never trigger dedup warning."""
    from app.orchestrator import _check_intra_batch_dedup

    topics = [{"title": "单篇测试", "keywords": ["test"], "keywords_cn": ["测试"], "score": 80}]
    clean, warnings = _check_intra_batch_dedup(topics)
    assert len(warnings) == 0
    assert len(clean) == 1
    print("  PASS test_dedup_single_topic_no_warning")


def test_dedup_empty_list():
    """Empty topic list should work fine."""
    from app.orchestrator import _check_intra_batch_dedup

    clean, warnings = _check_intra_batch_dedup([])
    assert len(warnings) == 0
    assert len(clean) == 0
    print("  PASS test_dedup_empty_list")


def test_dedup_low_overlap_passes():
    """Two topics sharing <40% keywords should not warn."""
    from app.orchestrator import _check_intra_batch_dedup

    topics = [
        {"title": "凯尔特人防守战术分析", "keywords": ["Celtics", "Defense", "Tactics", "NBA"],
         "keywords_cn": ["凯尔特人", "防守"], "score": 88},
        {"title": "某平台公布消费数据", "keywords": ["Retail", "Consumer", "Business", "China"],
         "keywords_cn": ["平台", "消费"], "score": 82},
    ]
    clean, warnings = _check_intra_batch_dedup(topics)
    # 两个话题的核心关键词没有交集。
    assert len(warnings) == 0, f"Expected 0 warnings, got: {warnings}"
    print("  PASS test_dedup_low_overlap_passes")


def test_dedup_prompt_has_core_subject_rule():
    """select_topics prompt must include intra-batch core-subject diversity rule."""
    import app.orchestrator as orch
    import inspect
    src = inspect.getsource(orch.select_topics)
    assert "不同核心主题" in src, "Prompt must require different core subjects"
    assert "核心关键词集合" in src, "Prompt must mention keyword set non-overlap"
    print("  PASS test_dedup_prompt_has_core_subject_rule")


def test_topic_selector_file_has_dedup_rule():
    """topic_selector.txt must include intra-batch dedup in 禁止选题 section."""
    from app.utils import load_prompt_template
    tmpl = load_prompt_template("topic_selector.txt", "basketball")
    assert "同一批次" in tmpl, "topic_selector.txt must mention intra-batch dedup"
    assert "核心关键词" in tmpl, "topic_selector.txt must mention core keyword diversity"
    print("  PASS test_topic_selector_file_has_dedup_rule")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Intra-Batch Dedup Tests")
    print("=" * 60)

    all_tests = [
        ("dedup: no overlap passes", test_dedup_no_overlap),
        ("dedup: high overlap warns", test_dedup_high_overlap_warns),
        ("dedup: single topic ok", test_dedup_single_topic_no_warning),
        ("dedup: empty list ok", test_dedup_empty_list),
        ("dedup: low overlap ok", test_dedup_low_overlap_passes),
        ("dedup: select_topics prompt has rule", test_dedup_prompt_has_core_subject_rule),
        ("dedup: topic_selector.txt has rule", test_topic_selector_file_has_dedup_rule),
    ]

    passed = 0
    failed = 0
    for name, test_fn in all_tests:
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR {name}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")
    sys.exit(0 if failed == 0 else 1)
