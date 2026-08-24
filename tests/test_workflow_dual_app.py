from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_scheduled_workflow_queues_finance_then_basketball():
    workflow = (ROOT / ".github" / "workflows" / "batch.yml").read_text(
        encoding="utf-8"
    )

    assert 'apps=["finance","basketball"]' in workflow
    assert "name: 1. 准备任务" in workflow
    assert "name: 2. 写文章 · ${{ matrix.app }}" in workflow
    assert "name: 3. 发布 · ${{ matrix.app }}" in workflow
    assert "needs: prepare" in workflow
    assert "needs: [prepare, write]" in workflow
    assert "max-parallel: 1" in workflow
    assert "group: toutiao-publish" in workflow


def test_manual_workflows_offer_both():
    for name in ("batch.yml", "daily.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )

        assert "default: both" in workflow
        assert "- both" in workflow
        assert "max-parallel: 1" in workflow


def test_both_workflows_persist_metadata_after_successful_publish():
    for name in ("batch.yml", "daily.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )

        assert "scripts/merge_batch_metadata.py" in workflow
        assert "git push origin HEAD:main" in workflow
