#!/usr/bin/env python3
"""从头条AI创作建议第一条直接生成并发布生活类微头条。"""

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

from constants import DASHSCOPE_KEY, DASHSCOPE_URL
from publisher import launch_browser, load_articles
from utils import call_llm, safe_json_loads


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env", override=False)
AUTH_FILE = Path(os.environ.get("TOUTIAO_AUTH_FILE", ROOT / "toutiao_auth.json"))
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", ROOT / "output"))
PUBLISH_URL = "https://mp.toutiao.com/profile_v4/weitoutiao/publish"
MANAGE_URL = "https://mp.toutiao.com/profile_v4/manage/content/all"
BATCHES = {"morning", "noon", "evening"}
BLOCKED_TERMS = (
    "法轮功", "法轮大法", "大纪元", "新唐人", "明慧网", "反华", "辱华",
    "台独", "港独", "藏独", "疆独", "falun gong", "falun dafa",
    "epoch times", "new tang dynasty", "minghui", "anti-china", "anti china",
)


def _security_passed(result):
    security = result.get("security") if isinstance(result, dict) else None
    return (isinstance(security, dict)
            and security.get("cult_or_extremist") is False
            and security.get("anti_china_or_hostile") is False)


def _validate_content(content, source_body):
    compact = re.sub(r"\s+", "", content or "")
    if not 220 <= len(compact) <= 350:
        raise ValueError(f"微头条长度异常: {len(compact)}字，应为220—350字")
    lowered = compact.lower()
    if any(term in lowered for term in BLOCKED_TERMS):
        raise ValueError("微头条命中邪教或反华黑名单")
    if "```" in content or content.lstrip().startswith(("标题：", "标题:")):
        raise ValueError("微头条包含标题或代码块")
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
    is_news = batch == "noon"
    style_rules = ("""这是一篇财经科技新闻。压缩成客观、清楚、有信息量的新闻微头条；只能使用原文事实，所有人物、机构、数字、日期、引语和因果必须来自原文，不得加入投资建议。开头直接给出最重要的信息，结尾可以说明这件事值得普通读者关注的原因，但不得增加原文外结论。"""
                   if is_news else
                   """这是一篇由头条AI第一条推荐话题生成的中年生活文章。压缩成第一人称生活微头条，保留具体场景、现实困境、行动转折和真实感悟；整体积极励志，可自然保留原文中挣钱、攒钱、普通人翻身或财富自由的内容，但不承诺暴富、不荐股、不鼓励借贷投机。""")

    prompt = f"""把下面这篇文章一次性改写成可直接发布的{('新闻' if is_news else '生活')}类微头条。

硬性要求：
1. {style_rules}
2. 正文220—350个中文字符，分3—5个短段落，不另写标题，不输出话题标签，不写“微头条：”。
3. 不得新增原文没有的数字，也不得改变原文事实、人物关系和不确定性。
4. 开头要让人愿意继续看，表达自然，不低俗、不标题党。
5. 内容安全只拦两类：邪教组织及其媒体宣传；反华、辱华、分裂中国或敌对攻击中国的叙事。其他普通生活和财富话题不得拒绝。
6. security两个字段必须明确返回布尔值；只有任一风险命中时content才为空。

只输出JSON：
{{"security":{{"cult_or_extremist":false,"anti_china_or_hostile":false,"reason":"明确理由"}},"content":"完整微头条正文"}}

原文标题：{topic}
原文正文：
{source_body[:7000]}
"""
    raw = call_llm(
        DASHSCOPE_URL, DASHSCOPE_KEY, "qwen-plus",
        [
            {"role": "system", "content": "你是严谨的今日头条短内容编辑。只输出JSON，只拦邪教宣传和反华敌对内容。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
        max_tokens=1800,
    )
    result = safe_json_loads(raw)
    if not _security_passed(result):
        security = result.get("security") if isinstance(result, dict) else None
        raise ValueError(f"内容安全未明确通过: {security}")
    content = str(result.get("content") or "").strip()
    _validate_content(content, source_body)

    output_dir = OUTPUT_DIR / date_str
    output_dir.mkdir(parents=True, exist_ok=True)
    draft = {
        "date": date_str,
        "batch": batch,
        "topic": topic,
        "content_type": "新闻微头条" if is_news else "生活微头条",
        "source_file": article.get("file", ""),
        "content": content,
        "generated_at": datetime.now().isoformat(),
    }
    draft_path = output_dir / f"micro-{batch}.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"微头条已生成: {draft_path} ({len(re.sub(r'\s+', '', content))}字)")
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
                    data = body.get("data") or body.get("Data") or {}
                    if isinstance(data, dict):
                        post_id = str(data.get("id") or data.get("group_id") or data.get("pgc_id") or "")
                    break
            if success:
                break
            page.wait_for_timeout(500)

        marker = draft["content"][:22]
        verified = False
        page.goto(MANAGE_URL, wait_until="domcontentloaded", timeout=60000)
        for _ in range(10):
            page.wait_for_timeout(1000)
            if marker in page.locator("body").inner_text():
                verified = True
                break
            page.reload(wait_until="domcontentloaded", timeout=60000)
        if not success or not verified:
            screenshot = OUTPUT_DIR / draft["date"] / f"micro-{draft['batch']}-failed.png"
            page.screenshot(path=str(screenshot), full_page=True)
            browser.close()
            raise RuntimeError(f"微头条未通过作品管理核验: 接口成功={success}")
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
