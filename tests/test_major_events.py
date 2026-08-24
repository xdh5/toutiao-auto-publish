"""NBA重大事件识别测试。"""

from orchestrator import detect_major_events


def fixture(home, away, home_score, away_score, status="FT"):
    return {"home_team": home, "away_team": away, "home_score": home_score,
            "away_score": away_score, "status": status, "league": "NBA"}


def match_data(*games):
    return {"fixtures_by_league": {"NBA": list(games)}}


def test_detect_high_scoring_game():
    events = detect_major_events(match_data(fixture("勇士", "湖人", 128, 125)))
    assert any(event["type"] == "对攻大战" for event in events)
    assert any("253分" in event["detail"] for event in events)


def test_detect_blowout():
    events = detect_major_events(match_data(fixture("雷霆", "太阳", 126, 98)))
    blowout = next(event for event in events if event["type"] == "大胜")
    assert blowout["urgency"] >= 70
    assert "28分差" in blowout["detail"]


def test_detect_close_finish():
    events = detect_major_events(match_data(fixture("凯尔特人", "尼克斯", 111, 110)))
    close = next(event for event in events if event["type"] == "决胜时刻")
    assert close["urgency"] >= 80


def test_normal_game_has_no_major_event():
    assert detect_major_events(match_data(fixture("火箭", "马刺", 112, 103))) == []


def test_unfinished_game_is_ignored():
    assert detect_major_events(match_data(fixture("湖人", "勇士", 80, 78, "LIVE"))) == []


def test_events_sorted_by_urgency():
    events = detect_major_events(match_data(
        fixture("勇士", "湖人", 128, 125),
        fixture("雷霆", "太阳", 130, 95),
    ))
    assert [e["urgency"] for e in events] == sorted((e["urgency"] for e in events), reverse=True)


def test_empty_data():
    assert detect_major_events({}) == []
