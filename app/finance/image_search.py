"""财经专用配图搜索。

图片只在最终文章生成成功后搜索。搜索词来自成文中的公司、产品、行业和
业务场景；不保存跨天图片历史，同一篇文章同一天重跑时保持候选顺序稳定。
"""

import hashlib
import re
from urllib.parse import quote_plus

import requests

from ..constants import UNSPLASH_KEY


_GENERIC_KEYWORDS = {
    "business", "company", "companies", "corporate", "economy", "economic",
    "finance", "financial", "market", "markets", "manufacturing", "industry",
    "technology", "innovation", "digital", "news", "china", "chinese",
}

_COMPANY_TERMS = (
    ("华为", "Huawei"), ("比亚迪", "BYD"), ("小米", "Xiaomi"),
    ("阿里巴巴", "Alibaba"), ("阿里", "Alibaba"), ("腾讯", "Tencent"),
    ("百度", "Baidu"), ("京东", "JD.com"), ("美团", "Meituan"),
    ("宁德时代", "CATL"), ("特斯拉", "Tesla"), ("苹果", "Apple"),
    ("英伟达", "NVIDIA"), ("微软", "Microsoft"), ("谷歌", "Google"),
    ("亚马逊", "Amazon"), ("台积电", "TSMC"), ("三星", "Samsung"),
)

_SCENE_TERMS = (
    (("新能源汽车", "电动车", "车企"), "electric vehicle factory"),
    (("汽车",), "automobile manufacturing factory"),
    (("芯片", "半导体", "晶圆"), "semiconductor chip manufacturing"),
    (("人工智能", "AI", "算力", "数据中心"), "artificial intelligence data center"),
    (("手机", "智能手机"), "smartphone manufacturing"),
    (("港口", "航运", "海运", "集装箱"), "cargo port shipping containers"),
    (("交通运输", "铁路", "高铁", "高速公路", "基建"), "transportation infrastructure China"),
    (("物流", "快递", "仓储"), "logistics warehouse distribution"),
    (("电商", "网购"), "ecommerce warehouse logistics"),
    (("零售", "消费", "商场"), "retail shopping consumers China"),
    (("银行", "金融", "保险"), "banking financial district"),
    (("房地产", "楼市", "住房"), "real estate construction China"),
    (("能源", "电力", "光伏", "风电", "储能"), "renewable energy power grid"),
    (("医药", "药企", "生物科技"), "pharmaceutical laboratory research"),
    (("农业", "粮食", "农产品"), "agriculture farming China"),
    (("制造业", "工厂", "生产线"), "manufacturing factory production line"),
)


def _deduplicate(values):
    result = []
    known = set()
    for value in values:
        clean = re.sub(r"\s+", " ", str(value or "")).strip()
        key = clean.lower()
        if clean and key not in known:
            known.add(key)
            result.append(clean)
    return result


def _specific_english_keywords(article):
    values = article.get("keywords", []) or []
    result = []
    for value in values:
        if not isinstance(value, str) or any("一" <= char <= "鿿" for char in value):
            continue
        clean = re.sub(r"[^A-Za-z0-9&.\- ]+", " ", value).strip()
        words = [word for word in clean.lower().split() if word]
        if clean and words and not all(word in _GENERIC_KEYWORDS for word in words):
            result.append(clean)
    return _deduplicate(result)


def build_search_queries(article):
    """从最终财经文章生成从具体到宽泛的英文图片搜索词。"""
    article = article if isinstance(article, dict) else {}
    text = " ".join(str(article.get(key) or "") for key in ("title", "content", "summary"))
    entities = [english for chinese, english in _COMPANY_TERMS if chinese in text]
    scenes = [scene for triggers, scene in _SCENE_TERMS if any(trigger in text for trigger in triggers)]
    keywords = _specific_english_keywords(article)

    primary_scene = scenes[0] if scenes else "business workplace China"
    queries = []
    if entities:
        queries.append(" ".join(entities[:2] + [primary_scene]))
    if keywords:
        queries.append(" ".join(keywords[:3] + [primary_scene]))
    queries.extend(scenes[:2])
    queries.append(primary_scene)
    return _deduplicate(queries)[:4]


def _stable_rotate(items, seed):
    """同一文章同一天顺序稳定，不同文章或日期轮换候选。"""
    values = list(items)
    if len(values) < 2:
        return values
    offset = int(hashlib.sha256(seed.encode("utf-8")).hexdigest(), 16) % len(values)
    return values[offset:] + values[:offset]


def search_images(article, count=5, date_str=None):
    """搜索最终财经文章的配图候选，不做跨天图片历史去重。"""
    article = article if isinstance(article, dict) else {}
    queries = build_search_queries(article)
    title = str(article.get("title") or "finance")
    images = []
    known_urls = set()

    if UNSPLASH_KEY:
        for query in queries:
            try:
                response = requests.get("https://api.unsplash.com/search/photos", params={
                    "query": query, "per_page": max(10, count * 2),
                    "orientation": "landscape", "client_id": UNSPLASH_KEY}, timeout=10)
                if response.status_code != 200:
                    continue
                results = _stable_rotate(
                    response.json().get("results", []),
                    f"{date_str or ''}|{title}|{query}",
                )
                for result in results:
                    url = result.get("urls", {}).get("regular", "")
                    if not url or url in known_urls:
                        continue
                    known_urls.add(url)
                    images.append({"url": url, "source": "unsplash",
                                   "alt": result.get("description") or result.get("alt_description") or query,
                                   "photo_id": result.get("id", ""), "query": query})
                    if len(images) >= count:
                        return images
            except (requests.RequestException, ValueError, KeyError):
                continue

    for query in queries:
        if len(images) >= count:
            break
        try:
            response = requests.get("https://duckduckgo.com/", params={"q": query}, timeout=10)
            match = re.search(r"vqd=([\d-]+)", response.text)
            if not match:
                continue
            response = requests.get(
                f"https://duckduckgo.com/i.js?q={quote_plus(query)}&vqd={match.group(1)}&o=json",
                timeout=10)
            if response.status_code != 200:
                continue
            results = _stable_rotate(
                response.json().get("results", []),
                f"{date_str or ''}|{title}|{query}|ddg",
            )
            for result in results:
                url = result.get("image", "")
                if not url or url in known_urls:
                    continue
                known_urls.add(url)
                images.append({"url": url, "source": "duckduckgo",
                               "alt": result.get("title", ""), "query": query})
                if len(images) >= count:
                    break
        except (requests.RequestException, ValueError):
            continue
    return images[:count]
