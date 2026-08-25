#!/usr/bin/env python3
"""Send one concise Telegram notification for a completed publish workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request


APP_LABELS = {
    "finance": "财经",
    "basketball": "篮球",
}


def parse_apps(raw: str) -> list[str]:
    try:
        apps = json.loads(raw)
    except json.JSONDecodeError:
        apps = [item.strip() for item in raw.split(",") if item.strip()]
    return [app for app in apps if app in APP_LABELS]


def app_phrase(apps: list[str]) -> str:
    return "/".join(APP_LABELS[app] for app in apps if app in APP_LABELS)


def success_text(apps: list[str]) -> str:
    return f"✅ {app_phrase(apps)}发布成功"


def failure_text(apps: list[str], run_url: str, reason: str = "") -> str:
    lines = [f"❌ {app_phrase(apps)}发布失败"]
    if run_url:
        lines.append(run_url)
    if reason:
        lines.append(reason)
    return "\n".join(lines)


def detect_published_apps(marker_root: Path, apps: list[str]) -> list[str]:
    published = []
    for app in apps:
        if any(app in path.parts for path in marker_root.glob("**/publish-success")):
            published.append(app)
    return published


def send_telegram(bot_token: str, chat_id: str, text: str, *, silent: bool) -> None:
    payload_dict = {
        "chat_id": chat_id,
        "text": text,
    }
    # Success must be a silent Telegram message. Failure must omit this field
    # so clients treat it as a normal system notification.
    if silent:
        payload_dict["disable_notification"] = True
    payload = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Telegram 通知发送失败：{exc}") from exc
    if not result.get("ok"):
        raise RuntimeError(f"Telegram 通知发送失败：{result.get('description', '未知错误')}")


def failed_steps(repository: str, run_id: str, github_token: str) -> list[str]:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs?per_page=100",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            jobs = json.loads(response.read().decode("utf-8")).get("jobs", [])
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return []

    failures: list[str] = []
    for job in jobs:
        if job.get("conclusion") not in {"failure", "cancelled", "timed_out"}:
            continue
        step = next(
            (
                item.get("name")
                for item in job.get("steps", [])
                if item.get("conclusion") in {"failure", "cancelled", "timed_out"}
            ),
            None,
        )
        failures.append(f"{job.get('name', '任务')} / {step or job.get('conclusion', '失败')}")
    return failures


def has_publish_marker(marker_root: Path) -> bool:
    return any(marker_root.glob("**/publish-success"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot-token", required=True)
    parser.add_argument("--chat-id", required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--github-token", required=True)
    parser.add_argument("--marker-root", type=Path, required=True)
    parser.add_argument("--prepare-result", required=True)
    parser.add_argument("--write-result", required=True)
    parser.add_argument("--publish-result", required=True)
    parser.add_argument("--apps", default='["finance","basketball"]')
    parser.add_argument("--run-url", default="")
    args = parser.parse_args()

    apps = parse_apps(args.apps) or ["finance", "basketball"]
    published = detect_published_apps(args.marker_root, apps)
    workflow_ok = all(
        result == "success"
        for result in (args.prepare_result, args.write_result, args.publish_result)
    )
    run_url = args.run_url or f"https://github.com/{args.repository}/actions/runs/{args.run_id}"

    if workflow_ok:
        # Scheduled retry runs that only detect an already-completed batch stay quiet.
        if not published:
            print("本次没有实际发布，跳过 Telegram 通知")
            return 0
        send_telegram(
            args.bot_token,
            args.chat_id,
            success_text(published),
            silent=True,
        )
        return 0

    failed = [app for app in apps if app not in published]
    if published:
        send_telegram(
            args.bot_token,
            args.chat_id,
            success_text(published),
            silent=True,
        )
    if failed:
        reasons = failed_steps(args.repository, args.run_id, args.github_token)
        reason = "；".join(reasons[:3]) if reasons else ""
        send_telegram(
            args.bot_token,
            args.chat_id,
            failure_text(failed, run_url, reason),
            silent=False,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
