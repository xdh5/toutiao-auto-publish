#!/usr/bin/env python3
"""公用微头条生成与发布入口。"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from .constants import CONTENT_APP
from .publisher import launch_browser, load_articles


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
AUTH_FILE = Path(os.environ.get("TOUTIAO_AUTH_FILE", ROOT / "toutiao_auth.json"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output"))
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/weitoutiao/publish"
BATCHES = {"morning", "noon", "evening"}


def generate_draft(date_str, batch):
    """读取文章改写时一并生成的微头条，不再单独调用模型。"""
    if batch not in BATCHES:
        raise ValueError(f"未知批次: {batch}")
    articles = load_articles(date_str, batch_filter=batch)
    if len(articles) != 1:
        raise ValueError(f"{date_str} {batch} 应有且仅有1篇文章，实际{len(articles)}篇")
    article = articles[0]
    topic = str(article.get("title") or "").strip()
    if not topic:
        raise ValueError("本批次文章标题为空")
    is_basketball = CONTENT_APP == "basketball"
    metadata_path = Path(article["file"]).parent / "metadata.json"
    if not metadata_path.exists():
        raise ValueError("缺少文章 metadata，无法读取同轮生成的微头条")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    article_index = str(article.get("index", ""))
    row = next((item for item in metadata.get("articles", [])
                if str(item.get("index", "")) == article_index), None)
    content = str((row or {}).get("micro_content") or "").strip()
    if not content:
        raise ValueError("文章改写结果没有返回 micro_content")

    output_dir = OUTPUT_DIR / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    draft = {
        "date": date_str,
        "batch": batch,
        "topic": topic,
        "content_type": "NBA微头条" if is_basketball else "新闻微头条",
        "source_file": article.get("file", ""),
        "content": content,
        "generated_at": datetime.now().isoformat(),
    }
    draft_path = output_dir / f"micro-{batch}.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    content_length = len(re.sub(r"\s+", "", content))
    print(f"微头条已生成: {draft_path} ({content_length}字)")
    return draft


def _write_metadata(draft, post_id=""):
    output_dir = OUTPUT_DIR / draft["date"]
    metadata_path = output_dir / "metadata.json"
    existing = {}
    if metadata_path.exists():
        try:
            existing = json.loads(metadata_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    batches = set(existing.get("batches_completed", []))
    batches.add(draft["batch"])
    posts = list(existing.get("micro_posts", []))
    posts = [item for item in posts if item.get("batch") != draft["batch"]]
    posts.append({
        "batch": draft["batch"], "topic": draft["topic"],
        "content_type": draft.get("content_type", "微头条"),
        "content": draft["content"], "post_id": post_id,
    })
    metadata = {
        **existing,
        "date": draft["date"],
        "generated_at": datetime.now().isoformat(),
        "total_articles": 0,
        "articles": [],
        "micro_posts": posts,
        "batches_completed": sorted(batches),
        "last_batch": draft["batch"],
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")


def publish(draft, headless=True, record_batch=True):
    """发布微头条，并在作品管理页核验正文开头。"""
    if not AUTH_FILE.exists():
        raise FileNotFoundError(f"登录状态不存在: {AUTH_FILE}")
    responses = []
    with sync_playwright() as playwright:
        browser = launch_browser(
            playwright,
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = browser.new_context(
            storage_state=str(AUTH_FILE), viewport={"width": 1280, "height": 900}, locale="zh-CN",
        )
        page = context.new_page()

        def capture(response):
            if "publish" not in response.url.lower():
                return
            if response.request.method.upper() != "POST":
                return
            try:
                body = response.json()
            except Exception:
                return
            responses.append({"url": response.url, "body": body})

        page.on("response", capture)
        page.goto(PUBLISH_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        if "/auth/" in page.url.lower() or "/login" in page.url.lower():
            browser.close()
            raise RuntimeError("头条登录状态已过期")

        editor = page.locator(".ProseMirror").first
        editor.wait_for(state="visible", timeout=20000)
        mask = page.locator(".publish-assistant-old-drawer .byte-drawer-mask").first
        try:
            if mask.is_visible(timeout=1000):
                mask.click(force=True, position={"x": 5, "y": 5})
                mask.wait_for(state="hidden", timeout=5000)
        except Exception:
            page.keyboard.press("Escape")
        editor.fill(draft["content"])

        publish_button = page.locator("button.publish-content").first
        publish_button.wait_for(state="visible", timeout=10000)
        if not publish_button.is_enabled():
            raise RuntimeError("微头条发布按钮不可用")
        responses.clear()
        publish_button.click()
        page.wait_for_timeout(1200)
        for label in ("确认发布", "确定", "继续发布"):
            button = page.get_by_role("button", name=label, exact=True).first
            try:
                if button.is_visible(timeout=500):
                    button.click()
                    break
            except Exception:
                pass

        deadline = time.time() + 20
        success = False
        post_id = ""
        while time.time() < deadline:
            for item in responses:
                body = item["body"]
                code = body.get("code", body.get("Code")) if isinstance(body, dict) else None
                if code == 0:
                    success = True
                    print(f"✅ 捕获发布接口成功: {item['url']}")
                    data = body.get("data") or body.get("Data") or {}
                    if isinstance(data, dict):
                        post_id = str(data.get("id") or data.get("group_id") or data.get("pgc_id") or "")
                    break
            if success:
                break
            page.wait_for_timeout(500)

        if not success:
            screenshot = OUTPUT_DIR / draft["date"] / f"micro-{draft['batch']}-failed.png"
            page.screenshot(path=str(screenshot), full_page=True)
            browser.close()
            codes = [item["body"].get("code") for item in responses if isinstance(item["body"], dict)]
            raise RuntimeError(f"未捕获发布接口code=0，响应代码={codes}")
        browser.close()

    if record_batch:
        _write_metadata(draft, post_id)
    else:
        print("ℹ️ 手动发布不记录批次完成状态")
    return post_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="日期 YYYY-MM-DD")
    parser.add_argument("--batch", required=True, choices=sorted(BATCHES))
    parser.add_argument("--show", action="store_true", help="只生成显示，不发布")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--no-record-batch", action="store_true",
                        help="发布成功后不占用早中晚批次名额")
    args = parser.parse_args()
    draft = generate_draft(args.date, args.batch)
    print(f"\n话题：{draft['topic']}\n\n{draft['content']}\n")
    if args.show:
        return 0
    post_id = publish(draft, headless=not args.headed,
                      record_batch=not args.no_record_batch)
    print(f"微头条发布成功 id={post_id or '接口未返回ID'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"微头条任务失败: {exc}", file=sys.stderr)
        sys.exit(1)
