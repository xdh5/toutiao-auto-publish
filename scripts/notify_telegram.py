#!/usr/bin/env python3
"""Send one concise Telegram notification for a completed publish workflow."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request


BATCH_LABELS = {
    "morning": "早",
    "noon": "中",
    "evening": "晚",
}


def send_telegram(bot_token: str, chat_id: str, text: str, *, silent: bool) -> None:
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": silent,
        },
        ensure_ascii=False,
    ).encode("utf-8")
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
    args = parser.parse_args()

    workflow_ok = all(
        result == "success"
        for result in (args.prepare_result, args.write_result, args.publish_result)
    )
    if workflow_ok:
        # Scheduled retry runs that only detect an already-completed batch stay quiet.
        if not has_publish_marker(args.marker_root):
            print("本次没有实际发布，跳过 Telegram 通知")
            return 0
        label = BATCH_LABELS.get(args.batch, args.batch)
        send_telegram(
            args.bot_token,
            args.chat_id,
            f"{label}发布已成功",
            silent=True,
        )
        return 0

    reasons = failed_steps(args.repository, args.run_id, args.github_token)
    reason = "；".join(reasons[:3]) if reasons else "工作流执行失败"
    send_telegram(
        args.bot_token,
        args.chat_id,
        f"发布失败：{reason}",
        silent=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
