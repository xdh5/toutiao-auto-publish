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


def test_only_scheduled_runs_persist_batch_completion():
    scheduled = (ROOT / ".github" / "workflows" / "batch.yml").read_text(
        encoding="utf-8"
    )
    manual = (ROOT / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8"
    )

    assert "scripts/merge_batch_metadata.py" in scheduled
    assert "github.event_name == 'schedule'" in scheduled
    assert "git push origin HEAD:main" in scheduled
    assert "scripts/merge_batch_metadata.py" not in manual
    assert "git push origin HEAD:main" not in manual


def test_manual_runs_never_read_or_record_batch_slots():
    scheduled = (ROOT / ".github" / "workflows" / "batch.yml").read_text(
        encoding="utf-8"
    )
    manual = (ROOT / ".github" / "workflows" / "daily.yml").read_text(
        encoding="utf-8"
    )

    assert "手动发布不读取也不占用早中晚批次名额" in scheduled
    assert "手动发布不读取也不占用早中晚批次名额" in manual
    assert "--no-record-batch" in scheduled
    assert "--no-record-batch" in manual


def test_publish_workflows_send_one_telegram_notification():
    for name in ("batch.yml", "daily.yml"):
        workflow = (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )

        assert "name: 4. Telegram 通知" in workflow
        assert "needs: [prepare, write, publish]" in workflow
        assert "scripts/notify_telegram.py" in workflow
        assert "secrets.TELEGRAM_BOT_TOKEN" in workflow
        assert "secrets.TELEGRAM_CHAT_ID" in workflow
        assert "pipeline/${{ matrix.app }}/publish-success" in workflow
