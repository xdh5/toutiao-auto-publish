import json
from pathlib import Path

from scripts import notify_telegram


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_success_text_is_one_sentence():
    assert notify_telegram.success_text(["finance", "basketball"]) == "✅ 财经/篮球发布成功"
    assert notify_telegram.success_text(["finance"]) == "✅ 财经发布成功"
    assert notify_telegram.success_text(["basketball"]) == "✅ 篮球发布成功"


def test_failure_text_includes_link_and_optional_reason():
    assert notify_telegram.failure_text(
        ["finance"],
        "https://github.com/example/repo/actions/runs/1",
        "写文章 · finance / 抓取素材并写文章",
    ) == (
        "❌ 财经发布失败\n"
        "https://github.com/example/repo/actions/runs/1\n"
        "写文章 · finance / 抓取素材并写文章"
    )
    assert notify_telegram.failure_text(
        ["basketball"],
        "https://github.com/example/repo/actions/runs/2",
        "",
    ) == "❌ 篮球发布失败\nhttps://github.com/example/repo/actions/runs/2"


def test_send_success_is_silent(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return _Response({"ok": True})

    monkeypatch.setattr(notify_telegram.urllib.request, "urlopen", fake_urlopen)
    notify_telegram.send_telegram("token", "chat", "早发布已成功", silent=True)

    assert captured == {
        "chat_id": "chat",
        "text": "早发布已成功",
        "disable_notification": True,
    }


def test_send_failure_requests_system_notification(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode("utf-8")))
        return _Response({"ok": True})

    monkeypatch.setattr(notify_telegram.urllib.request, "urlopen", fake_urlopen)
    notify_telegram.send_telegram("token", "chat", "发布失败：登录状态过期", silent=False)

    assert captured == {
        "chat_id": "chat",
        "text": "发布失败：登录状态过期",
    }
    assert "disable_notification" not in captured


def test_main_success_is_silent_and_failure_is_pushed(monkeypatch, tmp_path):
    captured = []

    def fake_urlopen(request, timeout):
        if "sendMessage" in request.full_url:
            captured.append(json.loads(request.data.decode("utf-8")))
            return _Response({"ok": True})
        return _Response({"jobs": [{"name": "3. 发布 · finance", "conclusion": "failure", "steps": []}]})

    monkeypatch.setattr(notify_telegram.urllib.request, "urlopen", fake_urlopen)

    marker = tmp_path / "pipeline" / "finance" / "publish-success"
    marker.parent.mkdir(parents=True)
    marker.touch()
    monkeypatch.setattr(
        "sys.argv",
        [
            "notify_telegram.py",
            "--bot-token", "token",
            "--chat-id", "chat",
            "--batch", "morning",
            "--repository", "owner/repo",
            "--run-id", "1",
            "--github-token", "gh",
            "--marker-root", str(tmp_path),
            "--prepare-result", "success",
            "--write-result", "success",
            "--publish-result", "success",
            "--apps", '["finance"]',
        ],
    )
    assert notify_telegram.main() == 0
    assert captured[0]["disable_notification"] is True
    assert captured[0]["text"] == "✅ 财经发布成功"

    captured.clear()
    monkeypatch.setattr(
        "sys.argv",
        [
            "notify_telegram.py",
            "--bot-token", "token",
            "--chat-id", "chat",
            "--batch", "morning",
            "--repository", "owner/repo",
            "--run-id", "1",
            "--github-token", "gh",
            "--marker-root", str(tmp_path / "empty"),
            "--prepare-result", "success",
            "--write-result", "success",
            "--publish-result", "failure",
            "--apps", '["finance"]',
            "--run-url", "https://github.com/owner/repo/actions/runs/1",
        ],
    )
    assert notify_telegram.main() == 0
    assert "disable_notification" not in captured[0]
    assert captured[0]["text"].startswith("❌ 财经发布失败")


def test_publish_marker_detection(tmp_path: Path):
    assert not notify_telegram.has_publish_marker(tmp_path)
    marker = tmp_path / "pipeline" / "finance" / "publish-success"
    marker.parent.mkdir(parents=True)
    marker.touch()
    assert notify_telegram.has_publish_marker(tmp_path)
