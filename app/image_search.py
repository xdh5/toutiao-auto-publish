"""财经与篮球共用的文章配图搜索。"""

import re
from urllib.parse import quote_plus

import requests

from .constants import UNSPLASH_KEY, WIKI_PLAYERS, WIKI_TEAMS


def search_wikipedia(entity_name, lang="en"):
    """搜索维基百科实体主图。"""
    try:
        response = requests.get(
            f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(entity_name)}",
            headers={"User-Agent": "ToutiaoPublisher/1.0"}, timeout=10)
        if response.status_code != 200:
            return []
        data = response.json()
        image = data.get("originalimage") or data.get("thumbnail")
        if image and image.get("source"):
            return [{"url": image["source"], "source": "wikipedia",
                     "alt": data.get("title", entity_name)}]
    except (requests.RequestException, ValueError):
        pass
    return []


def extract_search_entities(topic):
    """从话题中识别已配置的 NBA 球员和球队；财经话题会自然返回空列表。"""
    title = str(topic.get("title") or "")
    search_text = title + " " + " ".join(topic.get("keywords_cn", []))
    players = [{"cn": name, "wiki": page} for name, page in WIKI_PLAYERS.items() if name in search_text]
    teams = [{"cn": name, "wiki": page} for name, page in WIKI_TEAMS.items() if name in search_text]
    terms = [term.strip() for term in re.split(r"[？！：\s]+", title) if len(term.strip()) >= 2]
    return players, teams, " ".join(terms[:5]) or title


def search_images(topic, count=5):
    """按实体图、Unsplash、DuckDuckGo 的顺序寻找文章配图。"""
    images = []
    topic = topic if isinstance(topic, dict) else {}
    keywords = [item for item in topic.get("keywords", []) if isinstance(item, str)]
    english_keywords = [item for item in keywords if not any("一" <= char <= "鿿" for char in item)]
    players, teams, specific_query = extract_search_entities(topic)

    for entity in players[:2] + teams[:2]:
        for image in search_wikipedia(entity["wiki"]):
            if image["url"] not in {item["url"] for item in images}:
                images.append(image)

    core = " ".join(english_keywords[:4]) or specific_query or "business technology"
    if len(images) < count and UNSPLASH_KEY:
        try:
            response = requests.get("https://api.unsplash.com/search/photos", params={
                "query": core, "per_page": count - len(images), "orientation": "landscape",
                "client_id": UNSPLASH_KEY}, timeout=10)
            if response.status_code == 200:
                for result in response.json().get("results", []):
                    images.append({"url": result["urls"]["regular"], "source": "unsplash",
                                   "alt": result.get("description") or core})
        except (requests.RequestException, ValueError, KeyError):
            pass

    if len(images) < count:
        try:
            response = requests.get("https://duckduckgo.com/", params={"q": core}, timeout=10)
            match = re.search(r"vqd=([\d-]+)", response.text)
            if match:
                response = requests.get(
                    f"https://duckduckgo.com/i.js?q={quote_plus(core)}&vqd={match.group(1)}&o=json",
                    timeout=10)
                if response.status_code == 200:
                    known = {item["url"] for item in images}
                    for result in response.json().get("results", []):
                        url = result.get("image", "")
                        if url and url not in known:
                            images.append({"url": url, "source": "duckduckgo",
                                           "alt": result.get("title", "")})
                            known.add(url)
                        if len(images) >= count:
                            break
        except (requests.RequestException, ValueError):
            pass
    return images[:count]
