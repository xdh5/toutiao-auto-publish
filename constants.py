#!/usr/bin/env python3
"""NBA 自媒体 — 全局常量与配置

所有模块共享的常量、API key、URL、字典映射等。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 本地开发自动读取项目根目录 .env；系统环境变量/GitHub Secrets 优先。
load_dotenv(Path(__file__).parent / ".env", override=False)

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", PROJECT_ROOT / "output"))
GZH_SCRIPT = str(PROJECT_ROOT / "skills" / "gzh-explosive-content-detector" / "scripts" / "fetch_gzh_trends.py")

# --- API keys from env (GitHub Secrets) ---
# LLM provider: hy3 / 腾讯云 TokenHub（tencentmaas，OpenAI 兼容协议）
# 优先读 HY3_API_KEY，兼容旧变量 DEEPSEEK_API_KEY。
# ⚠️ 切勿在此硬编码真实 key：本仓库为 public，写死会泄露并被他人盗刷额度。
# 真实 key 通过 GitHub Actions Secrets (HY3_API_KEY) 注入 CI。
_HY3_DEFAULT_KEY = ""


def _resolve_api_key(default, *env_names):
    """按优先级从环境变量读取 API key。

    跳过空值、纯空白、以及占位符 '***'（CI 里未配置/打码占位的常见写法），
    回退到内置默认值。否则 '***' 会被原样注入 Authorization 头，
    requests 会因保留字符 '*' 直接抛 InvalidHeader，导致整批文章生成失败、发布全挂。
    """
    for name in env_names:
        v = (os.environ.get(name) or "").strip()
        if v and v != "***":
            return v
    return default


HY3_API_KEY = _resolve_api_key(_HY3_DEFAULT_KEY, "HY3_API_KEY", "DEEPSEEK_API_KEY")
HY3_BASE_URL = "https://tokenhub.tencentmaas.com/v1/chat/completions"
# 模型映射（可经环境变量覆盖）：TokenHub 仅 hy3 一个模型，flash/pro 均映射为 hy3
HY3_MODEL_FLASH = os.environ.get("HY3_MODEL_FLASH", "hy3")   # 对应原 deepseek-v4-flash
HY3_MODEL_PRO = os.environ.get("HY3_MODEL_PRO", "hy3")         # 对应原 deepseek-v4-pro

# DASHSCOPE（通义千问）作为 hy3 配额耗尽时的兜底，同样需要跳过占位符
DASHSCOPE_KEY = _resolve_api_key("", "DASHSCOPE_API_KEY")
UNSPLASH_KEY = os.environ.get("UNSPLASH_ACCESS_KEY", "")
WORLD_NEWS_API_KEY = _resolve_api_key("", "WORLD_NEWS_API_KEY")
WORLD_NEWS_URL = "https://api.worldnewsapi.com/search-news"
NBA_DATA_BASE = "https://www.zhibo8.com"
NBA_NEWS_BASE = "https://news.zhibo8.com/nba/"
NBA_STANDINGS_URL = "https://nba.hupu.com/standings"
NBA_PLAYERS_URL = "https://nba.hupu.com/stats/players"
# 兼容旧模块导入；NBA 版不再请求 football-data.org。
FOOTBALL_DATA_KEY = ""

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
FOOTBALL_DATA_BASE = NBA_DATA_BASE

# --- WxPusher ---
WXPUSHER_APPTOKEN = os.environ.get("WXPUSHER_APPTOKEN", "")
WXPUSHER_UID = os.environ.get("WXPUSHER_UID", "")

# 兼容旧调用的单赛事配置。
COMPETITION_IDS = {"NBA": "nba"}

# --- GZH (公众号) keyword groups for trending detection ---
GZH_KEYWORD_GROUPS = [
    "NBA,篮球", "NBA,季后赛,总决赛,常规赛",
    "NBA,绝杀,逆转,加时,爆冷", "NBA,交易,签约,续约,自由球员",
    "NBA,詹姆斯,库里,杜兰特,东契奇,约基奇",
    "NBA,三双,得分,篮板,助攻,三分",
]

GZH_TRANSFER_KEYWORDS = [
    "NBA交易,重磅交易,交易流言", "NBA签约,续约,自由球员,裁员",
    "NBA选秀,新秀,乐透签", "NBA球队,主教练,下课",
]

GZH_NOISE_PATTERNS = [
    "实况足球", "足球经理", "世界杯", "英超", "欧冠", "中超",
    "乒乓球", "樊振东", "孙颖莎", "王楚钦", "马龙", "国乒",
    "辽篮", "郭艾伦", "赵继伟", "CBA", "男篮国家队", "广东宏远", "华南虎",
    "和平精英", "王者荣耀", "英雄联盟", "LPL",
    # Non-sports
    "纳斯达克", "IPO", "股票", "基金", "利率",
    "GLM-", "AI模型", "大模型",
    # Chinese football drama (not match/tournament analysis)
    "董路", "宋凯",
    # Geopolitics/news (not football)
    "伊朗方面", "伊朗宣布",
    # Marketing/PR analysis (not football content)
    "品牌营销", "营销妙手", "营销格局",
]

# --- NBA Wikipedia entity mappings ---
WIKI_PLAYERS = {
    "詹姆斯": "LeBron_James", "勒布朗": "LeBron_James", "库里": "Stephen_Curry",
    "杜兰特": "Kevin_Durant", "东契奇": "Luka_Dončić", "约基奇": "Nikola_Jokić",
    "字母哥": "Giannis_Antetokounmpo", "亚历山大": "Shai_Gilgeous-Alexander",
    "爱德华兹": "Anthony_Edwards_(basketball)", "塔图姆": "Jayson_Tatum",
    "杰伦布朗": "Jaylen_Brown", "文班亚马": "Victor_Wembanyama",
    "哈登": "James_Harden", "伦纳德": "Kawhi_Leonard", "欧文": "Kyrie_Irving",
    "戴维斯": "Anthony_Davis", "布克": "Devin_Booker", "恩比德": "Joel_Embiid",
}

WIKI_TEAMS = {
    "湖人": "Los_Angeles_Lakers", "勇士": "Golden_State_Warriors", "凯尔特人": "Boston_Celtics",
    "雷霆": "Oklahoma_City_Thunder", "掘金": "Denver_Nuggets", "森林狼": "Minnesota_Timberwolves",
    "独行侠": "Dallas_Mavericks", "快船": "Los_Angeles_Clippers", "太阳": "Phoenix_Suns",
    "雄鹿": "Milwaukee_Bucks", "尼克斯": "New_York_Knicks", "骑士": "Cleveland_Cavaliers",
    "火箭": "Houston_Rockets", "马刺": "San_Antonio_Spurs", "热火": "Miami_Heat",
    "76人": "Philadelphia_76ers", "灰熊": "Memphis_Grizzlies", "国王": "Sacramento_Kings",
}

FOOTYRENDERS_PLAYERS = {}

# --- Batch content type assignments (Deprecated v1, kept for test compat) ---
BATCH_TYPES = {
    "morning": ["热点球评", "八卦趣事"],
    "noon": ["交易资讯", "排行榜"],
    "evening": ["战术解析", "八卦趣事"],
}

# --- Batch Column Configuration (v2: Column System) ---
# Each batch has 2 unique "columns" (栏目). A column defines the complete
# reader-facing identity: topic domain, writing format, tone, word count,
# and interaction pattern. Six columns, zero overlap across all batches.
#
# DATA SOURCE HINT per column:
#   "match_preferred" = try match data first, fall back to GZH
#   "gzh_preferred"   = try GZH first, enrich with match context if available
#   "gzh_only"         = always use GZH pool regardless of match availability

BATCH_CONFIG = {
    "morning": {
        "name": "晨读",
        "time": "08:00",
        "reader_scenario": "通勤/早咖啡，需要快速了解发生了什么",
        "overall_tone": "轻快、信息密度高、适合碎片化阅读",
        "slots": [
            {
                "slot": 0,
                "column_id": "chen-du-kuai-xun",
                "column_name": "NBA早报",
                "icon": "📰",
                "topic_domain": "NBA快讯",
                "topic_guidance": "3-5条最新NBA短消息加一句话辣评，可包含比赛结果、球星表现、伤病和交易动态。所有比分与球员数据必须来自素材。",
                "writing_style": "群聊播报体",
                "style_detail": "每条消息3-5句，格式为【事件概述】+一句话老六辣评。短句、快节奏、有信息量但不啰嗦。像一个人肉RSS但有态度。禁止长篇大论，每条独立成块。",
                "word_count": [300, 500],
                "interaction_type": "prediction_poll",
                "interaction_guidance": "文末围绕焦点比赛或交易消息做A/B预测投票，并先给判断。",
                "data_source_hint": "match_preferred",
            },
            {
                "slot": 1,
                "column_id": "hua-ti-lei-tai",
                "column_name": "话题擂台",
                "icon": "🥊",
                "topic_domain": "NBA争议话题",
                "topic_guidance": "围绕轮休、争议哨、球星地位、阵容选择或交易价值列出正反观点，最后明确站队并给出事实依据。",
                "writing_style": "烧烤摊辩论体",
                "style_detail": "先摆出争议话题（一句话定调）→ 正方观点（2-3个论据）→ 反方观点（2-3个论据）→ 老六站队（亮明态度+核心论据）→ 邀请读者站队。语气像烧烤摊上和朋友抬杠，可以激动但不说脏话。必须给双方都有说话的机会，但最后必须有你自己的态度。",
                "word_count": [400, 600],
                "interaction_type": "side_taking_vote",
                "interaction_guidance": "文末明确说'评论区站队——支持XX的扣1，反对的扣2，我先来：我站[1/2]，因为...'",
                "data_source_hint": "gzh_preferred",
            },
        ],
    },
    "noon": {
        "name": "午间",
        "time": "12:00",
        "reader_scenario": "午休刷手机，需要快速了解上午发生了什么",
        "overall_tone": "信息密度高、快节奏、适合午休碎片阅读",
        "slots": [
            {
                "slot": 0,
                "column_id": "wu-jian-kuai-xun",
                "column_name": "午间快讯",
                "icon": "⚡",
                "topic_domain": "NBA快讯",
                "topic_guidance": "上午最新NBA消息精选：比赛结果、球星数据、伤病、交易和突发事件。每条包含事实概述和一句话辣评。",
                "writing_style": "群聊播报体",
                "style_detail": "3-5条消息，每条3-5句。格式：【事件概述】+ 一句话老六辣评。短句、快节奏、有信息量但不啰嗦。每条独立成块。",
                "word_count": [300, 500],
                "interaction_type": "prediction_poll",
                "interaction_guidance": "文末放一个投票：'今天上午最劲爆的消息是？A.XX B.XX C.XX，我选A，你呢？'",
                "data_source_hint": "match_preferred",
            },
            {
                "slot": 1,
                "column_id": "re-dian-su-ping",
                "column_name": "热点速评",
                "icon": "🔥",
                "topic_domain": "NBA热点评论",
                "topic_guidance": "从比赛或新闻中选一个最值得聊的话题，快速给出有证据的观点。可以复盘一场比赛，也可以点评交易或球星表现。",
                "writing_style": "赛后快刀体",
                "style_detail": "直接砸观点不铺垫 → 2-3个论据支撑 → 亮明立场。像从沙发上跳起来说的第一句话，锋利不留余地。500字以内，短平快。",
                "word_count": [400, 600],
                "interaction_type": "side_taking_vote",
                "interaction_guidance": "文末说：'觉得我说得对的扣1，觉得我太极端的扣2，我先来：我扣1，因为...'",
                "data_source_hint": "match_preferred",
            },
        ],
    },
    "evening": {
        "name": "晚间",
        "time": "17:30",
        "reader_scenario": "下班通勤/晚饭后刷手机，需要爽感和谈资",
        "overall_tone": "有观点、有情绪、适合截图转发和评论区站队",
        "slots": [
            # Slots are dynamically selected from EVENING_COLUMN_POOL at runtime.
            # Defaults below act as fallback if dynamic selection fails.
            {
                "slot": 0,
                "column_id": "nba-daily",
                "column_name": "NBA赛场日报",
                "icon": "📰",
                "topic_domain": "NBA赛况汇总",
                "topic_guidance": "汇总当天NBA比赛的高光、冷门、绝杀和关键球员表现。按比赛分块，比分和球员数据严格取自素材。",
                "writing_style": "快讯集锦体",
                "style_detail": "按比赛分块，每场2-3句话加一个记忆点，开头总结今日NBA主旋律，不得补写素材未提供的技术统计。",
                "word_count": [400, 600],
                "interaction_type": "prediction_poll",
                "interaction_guidance": "文末预测明天比赛：'明天XX对XX，你觉得谁能赢？评论区下注，我先来——...'",
                "data_source_hint": "gzh_only",
            },
            {
                "slot": 1,
                "column_id": "laoliu-hot-take",
                "column_name": "老六辣评",
                "icon": "🔥",
                "topic_domain": "NBA热点辣评",
                "topic_guidance": "点评当天最热的NBA话题，可以分析球队操作、球员表现、教练轮换或媒体争议，但强结论必须有素材依据。",
                "writing_style": "脱口秀吐槽体",
                "style_detail": "像篮球吐槽大会的单人版。开篇直接开火，用事实当子弹，每句吐槽后跟一句事实依据。",
                "word_count": [400, 600],
                "interaction_type": "side_taking_vote",
                "interaction_guidance": "文末站队：'同意我的扣1，觉得我在瞎说的扣2，评论区见——别光扣数字，带理由来辩。'",
                "data_source_hint": "gzh_only",
            },
        ],
    },
}

# --- Evening Column Pool (晚间栏目池) ---
# The evening batch dynamically picks 2 columns from this pool based on daily
# GZH trending data. An LLM call scores each column against todayʼs hot topics
# and selects the two with the richest source material.
EVENING_COLUMN_POOL = [
    {
        "slot": -1,  # assigned at runtime
        "column_id": "nba-daily",
        "column_name": "NBA赛场日报",
        "icon": "📰",
        "topic_domain": "NBA赛况汇总",
        "topic_guidance": "汇总当天NBA比赛高光、冷门、绝杀和关键球员表现，比分和数据严格来自素材。",
        "writing_style": "快讯集锦体",
        "style_detail": "按比赛分块，每块2-3句话加一个记忆点，开头总结今日NBA主旋律。",
        "word_count": [400, 600],
        "interaction_type": "prediction_poll",
        "interaction_guidance": "文末预测明天比赛：'明天XX对XX，你觉得谁能赢？评论区下注，我先来——...'",
        "data_source_hint": "gzh_only",
    },
    {
        "slot": -1,
        "column_id": "laoliu-hot-take",
        "column_name": "老六辣评",
        "icon": "🔥",
        "topic_domain": "NBA热点辣评",
        "topic_guidance": "对当天最热的NBA球队操作、球员表现或教练决策给出有事实依据的犀利观点。",
        "writing_style": "脱口秀吐槽体",
        "style_detail": "像篮球吐槽大会的单人版，观点锋利但所有数据和事件都必须来自素材。",
        "word_count": [400, 600],
        "interaction_type": "side_taking_vote",
        "interaction_guidance": "文末站队：'同意我的扣1，觉得我在瞎说的扣2，评论区见——别光扣数字，带理由来辩。'",
        "data_source_hint": "gzh_only",
    },
    {
        "slot": -1,
        "column_id": "referee-room",
        "column_name": "争议裁判室",
        "icon": "🟥",
        "topic_domain": "裁判争议与规则讨论",
        "topic_guidance": "分析NBA争议哨、挑战、最后两分钟判罚、恶意犯规或驱逐，讲清规则和比赛影响。素材没有的画面细节不得补写。",
        "writing_style": "慢镜回放体",
        "style_detail": "像在回放中心看慢镜，先复述素材明确记载的画面，再分析规则依据并给出判断。",
        "word_count": [400, 600],
        "interaction_type": "side_taking_vote",
        "interaction_guidance": "文末投票：你认为这次判罚正确吗？正确扣1，错误扣2。",
        "data_source_hint": "gzh_only",
    },
    {
        "slot": -1,
        "column_id": "trade-radar",
        "column_name": "交易雷达",
        "icon": "📡",
        "topic_domain": "NBA交易与签约",
        "topic_guidance": "追踪交易、签约、续约、自由球员和选秀消息，分析阵容需求与影响，区分官宣、可靠报道和流言。",
        "writing_style": "总经理分析体",
        "style_detail": "按消息来源、阵容需求、薪资影响、成行可能性和后果展开，不把流言写成事实。",
        "word_count": [400, 600],
        "interaction_type": "prediction_poll",
        "interaction_guidance": "文末预测：你觉得这笔交易能成吗？能扣1，不能扣2。",
        "data_source_hint": "gzh_only",
    },
    {
        "slot": -1,
        "column_id": "fan-life",
        "column_name": "球迷众生相",
        "icon": "🎭",
        "topic_domain": "球迷文化与场外趣事",
        "topic_guidance": "选择真实的NBA球迷反应、看台趣事、球员与球迷互动或场外故事，素材没有的社交媒体评论不得编造。",
        "writing_style": "人间观察体",
        "style_detail": "像在球场边观察人间百态。用细节和画面说话，少评论多展示。可以有幽默感但不能嘲笑球迷的真情实感。每个故事要有画面感，让读者觉得'我也在现场就好了'。",
        "word_count": [400, 600],
        "interaction_type": "share_your_story",
        "interaction_guidance": "文末邀请分享：'你在现场看过最难忘的一场比赛是什么？评论区说说，看看谁的回忆最绝。'",
        "data_source_hint": "gzh_only",
    },
    # 交易密探：NBA交易、签约与自由球员动态
    {
        "slot": -1,
        "column_id": "trade-scout",
        "column_name": "交易密探",
        "icon": "🔍",
        "topic_domain": "NBA交易传闻与签约",
        "topic_guidance": "汇总最新交易、续约、自由球员和裁员消息，每条说明来源、涉及球队、进展与影响。",
        "writing_style": "交易流言快报体",
        "style_detail": "每条2-4句话：球员和球队、条件、进展、点评；传闻必须明确标注。",
        "word_count": [400, 600],
        "interaction_type": "voting",
        "interaction_guidance": "文末投票：'这交易你打几分？1-5分，评论区告诉我，我先来——'",
        "data_source_hint": "transfer_preferred",
    },
]

# Map new column names to legacy content types for metadata compatibility
CONTENT_TYPE_TO_COLUMN = {
    "NBA早报": "热点球评",
    "话题擂台": "八卦趣事",
    "数据盘点": "排行榜",
    "深水区": "战术解析",
    # Evening pool (动态选择)
    "NBA赛场日报": "热点球评",
    "老六辣评": "八卦趣事",
    "争议裁判室": "八卦趣事",
    "交易雷达": "交易资讯",
    "交易密探": "交易资讯",
    "球迷众生相": "八卦趣事",
}

# --- Data availability fallback ---
FALLBACK_MAP = {
    "热点球评": "战术解析",
    "排行榜": "八卦趣事",
}

# --- All content types ---
ALL_CONTENT_TYPES = ["八卦趣事", "交易资讯", "战术解析", "热点球评", "排行榜"]

# --- Weekly Column Rotation (周一=0, 周日=6) ---
# Each day has a column theme that layers on top of one article in the batch
WEEKLY_COLUMNS = {
    0: {"slug": "du-she-bang", "name": "毒舌榜", "icon": "🔪",
        "description": "带排名的犀利点评，不是Excel是态度",
        "best_with": ["排行榜", "热点球评"],
        "style": "排名体：每个条目3-5句话，毒舌但不刻薄，用对比制造笑点，最后一句必须是让人忍不住截图的吐槽"},
    1: {"slug": "zhan-shu-hei-ban", "name": "战术黑板", "icon": "📋",
        "description": "把复杂战术翻译成球迷能吹牛的大白话",
        "best_with": ["战术解析"],
        "style": "教书体：先抛一个反常识的战术发现，然后用生活类比解释（'就像打游戏选错装备一样'），最后给一个能记住的结论"},
    2: {"slug": "trade-room", "name": "交易茶水间", "icon": "☕",
        "description": "NBA交易与签约的通俗解读",
        "best_with": ["交易资讯", "八卦趣事"],
        "style": "明确区分官宣、可靠报道和推测，聊清阵容需求与薪资影响"},
    3: {"slug": "hui-yi-sha", "name": "老六回忆杀", "icon": "📼",
        "description": "勾起球迷共同记忆的怀旧故事",
        "best_with": ["八卦趣事", "热点球评"],
        "style": "故事体：从一个具体的画面或瞬间切入（'我还记得那天穿着谁的球衣'），用细节勾回忆，以怀旧但不煽情的语气收尾，让读者在评论区晒自己的记忆"},
    4: {"slug": "zhou-mo-yu-re", "name": "周末预热", "icon": "🔥",
        "description": "本周末最值得关注的比赛，制造期待感",
        "best_with": ["热点球评", "战术解析"],
        "style": "预告体：像在群里约球友看球，列出'为什么这场必看'的3个理由（必须有一个跟数据无关、跟情绪有关的理由），结尾号召评论区晒看球计划"},
    5: {"slug": "sai-hou-kuai-dao", "name": "赛后快刀", "icon": "⚡",
        "description": "比赛结束后的第一时间犀利点评",
        "best_with": ["热点球评", "八卦趣事"],
        "style": "快刀体：开头直击最刺激的30秒画面，不铺垫不废话，观点锋利不留余地，像刚看完球从沙发上跳起来说的第一句话"},
    6: {"slug": "zhou-mo-fu-pan", "name": "周末复盘", "icon": "🔍",
        "description": "周末比赛的整体回顾和趋势洞察",
        "best_with": ["战术解析", "排行榜"],
        "style": "复盘体：从一个被大多数人忽略的数据或画面切入，串联周末多场比赛提炼一个共同趋势，让读者感觉'这个角度我怎么没想到'"},
}

# 财经版只替换栏目内容；调度、选图、保存和发布仍使用原流程。
BATCH_CONFIG = {
    "morning": {
        "name": "晨读", "time": "08:00", "reader_scenario": "早间国内商业资讯",
        "overall_tone": "简洁、客观、信息密度高",
        "slots": [{"slot": 0, "column_id": "finance-news-morning", "column_name": "国内财经科技新闻", "icon": "📰",
                   "topic_domain": "国内财经与科技新闻", "topic_guidance": "选择business或technology类别中信息最完整的一条",
                   "writing_style": "商业新闻体", "style_detail": "忠实来源、简洁客观，不增加来源外的人物、数字、引语或结论",
                   "word_count": [1, 500], "interaction_type": "", "interaction_guidance": "",
                   "data_source_hint": "news"}]},
    "noon": {
        "name": "午间", "time": "12:00", "reader_scenario": "午间海外商业资讯",
        "overall_tone": "简洁、客观、信息密度高",
        "slots": [{"slot": 0, "column_id": "finance-news-noon", "column_name": "财经科技新闻", "icon": "🌐",
                   "topic_domain": "与中国读者相关的海外财经与科技新闻", "topic_guidance": "选择business或technology类别中信息最完整的一条",
                   "writing_style": "商业新闻体", "style_detail": "忠实来源、简洁客观，不增加来源外的人物、数字、引语或结论",
                   "word_count": [1, 500], "interaction_type": "", "interaction_guidance": "",
                   "data_source_hint": "news"}]},
    "evening": {
        "name": "晚间", "time": "17:30", "reader_scenario": "晚间国内商业资讯",
        "overall_tone": "简洁、客观、信息密度高",
        "slots": [{"slot": 0, "column_id": "finance-news-evening", "column_name": "国内财经科技新闻", "icon": "💼",
                   "topic_domain": "国内财经与科技新闻", "topic_guidance": "选择business或technology类别中信息最完整且早间未发布的一条",
                   "writing_style": "商业新闻体", "style_detail": "忠实来源、简洁客观，不增加来源外的人物、数字、引语或结论",
                   "word_count": [1, 500], "interaction_type": "", "interaction_guidance": "",
                   "data_source_hint": "news"}]},
}

CONTENT_TYPE_TO_COLUMN.update({"国内商业": "国内商业", "海外商业": "海外商业", "科技动态": "科技动态"})
