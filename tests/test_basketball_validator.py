from app.basketball.validator import validate_match_data, validate_source_fidelity


def test_basketball_source_validator_rejects_invented_triple_double():
    fixture = {"article_text": "球员得到20分。", "player_stats": [{
        "player": "球员", "points": 20, "rebounds": 5, "assists": 4,
    }]}
    passed, issues = validate_source_fidelity(
        fixture, {"title": "比赛结束", "content": "球员拿下三双。"})
    assert passed is False
    assert "新增编造: 三双" in issues


def test_basketball_match_validator_rejects_wrong_score_and_stats():
    fixture = {
        "home_team": "甲队", "away_team": "乙队", "home_score": 110, "away_score": 105,
        "player_stats": [{"player": "张三", "points": 30, "rebounds": 8, "assists": 6}],
    }
    passed, issues = validate_match_data(
        fixture, {"title": "甲队对乙队", "content": "比分为100-90，张三得到25分。"})
    assert passed is False
    assert any("比分不一致" in issue for issue in issues)
    assert any("张三分不一致" in issue for issue in issues)
