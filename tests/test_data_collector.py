"""NBA数据采集与事实结构测试。"""

from app.basketball.collector import fetch_fallback_trends
from app.basketball.media_scraper import SportsScraper
from app.utils import load_prompt_template


def test_homepage_parser_keeps_nba_only():
    html = """
    <div class="schedule"><ul>
      <li data-type="basketball" data-time="2026-10-20 08:00" label="篮球,NBA,湖人,勇士">
        <span class="_league">NBA常规赛</span><span class="_teams">湖人 <i>-</i> 勇士</span>
        <a href="/zhibo/nba/2026/match1v.htm">文字</a>
      </li>
      <li data-type="basketball" data-time="2026-10-20 09:00" label="篮球,WNBA,自由人,王牌">
        <span class="_league">WNBA常规赛</span><span class="_teams">自由人 <i>-</i> 王牌</span>
        <a href="/zhibo/nba/2026/match2v.htm">文字</a>
      </li>
      <li data-type="basketball" data-time="2026-10-20 10:00" label="篮球,CBA,广东,辽宁">
        <span class="_league">CBA常规赛</span><span class="_teams">广东 <i>-</i> 辽宁</span>
        <a href="/zhibo/nba/2026/match3v.htm">文字</a>
      </li>
    </ul></div>
    """
    games = SportsScraper()._parse_zhibo8_homepage(html, "2026-10-20")
    assert len(games) == 1
    assert games[0]["league"] == "NBA"
    assert games[0]["home_team"] == "湖人"


def test_fallback_uses_basketball_thresholds():
    data = {"all_fixtures": [{"home_team": "勇士", "away_team": "湖人", "league": "NBA",
                              "home_score": 128, "away_score": 125}]}
    topics = fetch_fallback_trends(data)
    titles = " ".join(topic["title"] for topic in topics)
    assert "对攻大战" in titles
    assert "NBA赛场日报" in titles
    assert "进球" not in titles


def test_player_stats_extraction():
    text = "东契奇砍下35分12篮板10助攻，带队取胜。"
    stats = SportsScraper._extract_player_stats_from_text(text)
    assert stats[0]["points"] == 35
    assert stats[0]["rebounds"] == 12
    assert stats[0]["assists"] == 10


def test_nba_prompt_files_load():
    selector = load_prompt_template("topic_selector.txt", "basketball")
    generator = load_prompt_template("article_generator.txt", "basketball")
    rewrite = load_prompt_template("rewrite_article.txt", "basketball")
    assert all("NBA" in prompt for prompt in (selector, generator, rewrite))
