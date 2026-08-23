# 头条号自动内容发布系统

每日自动生成并发布三篇今日头条文章：

- 08:00：读取头条创作助手第一条建议，生成中年励志生活文章。
- 12:00：采集与中国读者相关的海外 `business` / `technology` 新闻。
- 17:30：读取头条创作助手第一条建议，生成中年励志生活文章。

生活文章采用中年人第一人称，围绕挣钱、攒钱、普通人翻身和财富自由展开，正文约 450—550 字，标题限制在 2—30 字。新闻内容保留原有配图与发布流程。所有内容都会在生成前后拦截邪教来源及反华、辱华、分裂中国等内容。

## 自动流程

1. 早晚从头条创作助手读取第一条话题；中午从 World News API 读取财经科技新闻。
2. 调用通义千问生成文章或处理新闻。
3. 使用 Unsplash 搜索配图，没有合适图片时允许无图发布。
4. 使用 Playwright 登录头条创作后台并自动发布。
5. 将批次元数据回写仓库，用于每日三批次幂等控制。

## 本地运行

```bash
pip install -r requirements.txt
playwright install chromium

# 生成指定批次
python orchestrator.py 2026-08-24 --batch=morning
python orchestrator.py 2026-08-24 --batch=noon
python orchestrator.py 2026-08-24 --batch=evening

# 发布指定批次
python publisher.py 2026-08-24 --headless --batch=morning
```

## GitHub Actions Secrets

| 名称 | 用途 |
|---|---|
| `DASHSCOPE_API_KEY` | 通义千问生成与内容安全判断 |
| `WORLD_NEWS_API_KEY` | 中午财经科技新闻 |
| `UNSPLASH_ACCESS_KEY` | 文章配图 |
| `TOUTIAO_AUTH_GZ` | gzip + Base64 编码后的头条登录状态 |
| `WXPUSHER_APPTOKEN` | 运行结果通知，可选 |
| `WXPUSHER_UID` | 通知接收人，可选 |
| `HY3_API_KEY` | 旧流程兼容模型，可选 |

本地 `.env` 与 `toutiao_auth.json` 已被 Git 忽略，不会提交到仓库。

## 工作流

- `.github/workflows/batch.yml`：每天早、午、晚定时生成并发布。
- `.github/workflows/daily.yml`：手动触发和紧急补发。
- `.github/workflows/heartbeat.yml`：检查每日批次是否全部完成。

定时任务按北京时间运行。GitHub Actions 的 cron 使用 UTC，并设置了多个错峰触发点；同一批次成功后，后续触发会自动跳过。
