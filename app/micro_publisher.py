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

from .constants import DASHSCOPE_KEY, DASHSCOPE_URL, CONTENT_APP
from .publisher import launch_browser, load_articles
from .utils import call_llm, load_prompt_template, safe_json_loads


ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
AUTH_FILE = Path(os.environ.get("TOUTIAO_AUTH_FILE", ROOT / "toutiao_auth.json"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output"))
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/weitoutiao/publish"
BATCHES = {"morning", "noon", "evening"}
def _validate_content(content, source_body):
    compact = re.sub(r"\s+", "", content or "")
    min_chars, max_chars = (180, 300) if CONTENT_APP == "basketball" else (220, 350)
    if not min_chars <= len(compact) <= max_chars:
        raise ValueError(f"微头条长度异常: {len(compact)}字，应为{min_chars}—{max_chars}字")
    if "```" in content or content.lstrip().startswith(("标题：", "标题:")):
        raise ValueError("微头条包含标题或代码块")
    hashtags = re.findall(r"#[^#\n]{2,20}#", content)
    if not 1 <= len(hashtags) <= 2:
        raise ValueError(f"微头条应带1—2个话题标签，实际{len(hashtags)}个")
    if CONTENT_APP == "basketball" and not any(mark in content for mark in ("？", "?")):
        raise ValueError("篮球微头条缺少文末互动问题")
    source_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", source_body))
    output_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", content))
    invented = sorted(output_numbers - source_numbers)
    if invented:
        raise ValueError(f"微头条新增了原文没有的数字: {invented}")


def generate_draft(date_str, batch):
    """把本批次唯一一篇文章一次生成对应类型的微头条。"""
    if batch not in BATCHES:
        raise ValueError(f"未知批次: {batch}")
    articles = load_articles(date_str, batch_filter=batch)
    if len(articles) != 1:
        raise ValueError(f"{date_str} {batch} 应有且仅有1篇文章，实际{len(articles)}篇")
    article = articles[0]
    topic = str(article.get("title") or "").strip()
    source_body = str(article.get("body") or "").strip()
    if not topic or not source_body:
        raise ValueError("本批次文章标题或正文为空")
    is_basketball = CONTENT_APP == "basketball"
    prompt_template = load_prompt_template("micro_post.txt")
    system_prompt = load_prompt_template("micro_post_system.txt", "common")
    if not prompt_template or not system_prompt:
        raise ValueError("缺少微头条 Prompt")
    content = ""
    last_error = ""
    for attempt in range(3):
        retry_note = (f"\n上一次生成未通过：{last_error}。这次必须修正并重新输出完整正文。"
                      if last_error else "")
        prompt = prompt_template.format(
            topic=topic,
            source_body=source_body[:7000],
            retry_block=retry_note,
        )
        raw = call_llm(
            DASHSCOPE_URL, DASHSCOPE_KEY, "qwen-plus",
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1800,
        )
        result = safe_json_loads(raw)
        content = str(result.get("content") or "").strip()
        try:
            _validate_content(content, source_body)
            break
        except ValueError as exc:
            last_error = str(exc)
            if attempt == 2:
                raise
            print(f"微头条第{attempt + 1}次生成未通过，自动重写：{last_error}")

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


def publish(draft, headless=True):
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

    _write_metadata(draft, post_id)
    return post_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="日期 YYYY-MM-DD")
    parser.add_argument("--batch", required=True, choices=sorted(BATCHES))
    parser.add_argument("--show", action="store_true", help="只生成显示，不发布")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    draft = generate_draft(args.date, args.batch)
    print(f"\n话题：{draft['topic']}\n\n{draft['content']}\n")
    if args.show:
        return 0
    post_id = publish(draft, headless=not args.headed)
    print(f"微头条发布成功 id={post_id or '接口未返回ID'}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"微头条任务失败: {exc}", file=sys.stderr)
        sys.exit(1)
