# 头条号财经与篮球自动发布系统

同一仓库维护财经和“岛哥侃篮球”两套业务，共用头条登录、编辑器填写、图片上传、发布接口监听和幂等控制。通过 `CONTENT_APP=finance|football` 完全隔离采集、栏目、提示词、微头条规则和输出目录。

财经每日自动生成并发布三篇今日头条文章，并在每篇文章发布成功后追加一条对应微头条：

- 08:00：采集国内 `business` / `technology` 新闻。
- 12:00：采集与中国读者相关的海外 `business` / `technology` 新闻。
- 17:30：采集当天尚未发布的国内 `business` / `technology` 新闻。

三批正篇无论来源长短均由千问写成450—550字中文新闻，英文来源先翻译为中文；三批微头条均压缩为220—350字。每篇正篇最多使用1张配图，找不到合适图片时允许无图发布。每天合计发布3篇文章和3条微头条。

原有中年生活文章生成实现继续保留，但当前定时流程不调用。新闻内容保留原有配图与发布流程。

篮球业务沿用原项目的 NBA 赛程、战报、排名、交易与热点采集，以及“岛哥”文章和 NBA 微头条规则。财经与篮球的元数据分别保存在 `output/finance/` 和 `output/football/`，不会互相去重或覆盖。

## 自动流程

1. 早晚从 World News API 读取国内财经科技新闻；中午读取与中国读者相关的海外财经科技新闻。
2. 调用通义千问生成文章或处理新闻。
3. 使用 Unsplash 搜索配图，没有合适图片时允许无图发布。
4. 使用 Playwright登录头条创作后台并发布长文章。
5. 长文章成功后，生成同类型微头条并通过微头条发布页提交；作品管理页核验成功才算发布完成。
6. 将批次元数据回写仓库，用于每日三批次幂等控制。

## 本地运行

```bash
pip install -r requirements.txt
playwright install chromium

# 生成指定批次
$env:CONTENT_APP="finance"   # PowerShell；篮球改为 football
$env:OUTPUT_DIR="output/finance"
python orchestrator.py 2026-08-24 --batch=morning --count=1

# 发布指定批次
python publisher.py 2026-08-24 --headless --batch=morning

# 根据该批次文章生成并发布对应微头条
python micro_publisher.py 2026-08-24 --batch=morning
```

## GitHub Actions Secrets

| 名称 | 用途 |
|---|---|
| `FINANCE_TOUTIAO_AUTH_GZ` | 财经头条号登录状态 |
| `FOOTBALL_TOUTIAO_AUTH_GZ` | 篮球头条号登录状态 |
| `FINANCE_DASHSCOPE_API_KEY` | 财经通义千问 |
| `FOOTBALL_DASHSCOPE_API_KEY` | 篮球通义千问 |
| `FINANCE_WORLD_NEWS_API_KEY` | 财经 World News |
| `FINANCE_UNSPLASH_ACCESS_KEY` | 财经配图 |
| `FOOTBALL_UNSPLASH_ACCESS_KEY` | 篮球配图 |

GitHub 的统一批次工作流支持单独选择 `app` 和 `batch`，也支持 `app=both`。自动早、午、晚批次会同时为财经和篮球准备任务，两个账号进入共同并发队列逐个发布，不会同时操作头条后台。工作流界面分为“1. 准备任务 → 2. 写文章 → 3. 发布”三个阶段。

| `WXPUSHER_APPTOKEN` | 运行结果通知，可选 |
| `WXPUSHER_UID` | 通知接收人，可选 |

本地 `.env` 与 `toutiao_auth.json` 已被 Git 忽略，不会提交到仓库。

## 工作流

- `.github/workflows/batch.yml`：每天早、午、晚定时生成并发布。
- `.github/workflows/daily.yml`：手动触发和紧急补发。
- `.github/workflows/heartbeat.yml`：检查每日批次是否全部完成。

定时任务按北京时间运行。GitHub Actions 的 cron 使用 UTC，并设置了多个错峰触发点；同一批次成功后，后续触发会自动跳过。
