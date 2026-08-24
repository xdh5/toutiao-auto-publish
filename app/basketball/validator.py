"""篮球专用复核：检查来源忠实度和结构化比赛数据。"""

import re


def validate_source_fidelity(source_fixture, article):
    issues = []
    content = article.get("content", "") + article.get("title", "")
    source_text = source_fixture.get("article_text", "")
    expected_hg = source_fixture.get("home_score")
    expected_ag = source_fixture.get("away_score")
    if expected_hg is not None and expected_ag is not None:
        found_scores = re.findall(r'(\d+)[:-](\d+)', content)
        if found_scores and not any(
                (int(a) == expected_hg and int(b) == expected_ag)
                or (int(a) == expected_ag and int(b) == expected_hg)
                for a, b in found_scores):
            issues.append(f"比分不一致: 来源 {expected_hg}-{expected_ag}")

    player_stats = source_fixture.get("player_stats", [])
    for stat in player_stats:
        player = stat.get("player", "")
        if player and player in source_text and player not in content:
            issues.append(f"缺少球员: {player}")

    known_triple_double = any(
        sum(1 for key in ("points", "rebounds", "assists") if (stat.get(key) or 0) >= 10) >= 3
        for stat in player_stats)
    for pattern, description in (
            (r'三双', '新增编造: 三双'),
            (r'准三双', '新增编造: 准三双'),
            (r'命中\d+记三分', '新增编造: 三分命中数'),
            (r'第[一二三四]节.*?\d+分', '新增编造: 单节得分')):
        if not re.search(pattern, content):
            continue
        if pattern == r'三双' and known_triple_double:
            continue
        if not re.search(pattern, source_text):
            issues.append(description)

    return len(issues) == 0, issues


def validate_match_data(source_fixture, article):
    issues = []
    content = article.get("content", "") + article.get("title", "")
    home = source_fixture.get("home_team", "")
    away = source_fixture.get("away_team", "")
    home_score = source_fixture.get("home_score")
    away_score = source_fixture.get("away_score")

    if home and home not in content:
        issues.append(f"缺少主队名: {home}")
    if away and away not in content:
        issues.append(f"缺少客队名: {away}")
    if home_score is not None and away_score is not None:
        score_found = any(
            (int(match.group(1)) == home_score and int(match.group(2)) == away_score)
            or (int(match.group(1)) == away_score and int(match.group(2)) == home_score)
            for match in re.finditer(r'(\d+)\s*[-–:]\s*(\d+)', content))
        if not score_found and f"{home_score}-{away_score}" not in content.replace(" ", ""):
            issues.append(f"比分不一致: 比赛数据 {home} {home_score}-{away_score} {away}，但文中未出现该比分")

    for stat in source_fixture.get("player_stats", []):
        player = stat.get("player", "")
        if not player:
            continue
        for key, label in (("points", "分"), ("rebounds", "篮板"), ("assists", "助攻")):
            expected = stat.get(key)
            if expected is None:
                continue
            claim = re.search(rf'{re.escape(player)}[^。；]{{0,25}}?(\d{{1,2}}){label}', content)
            if claim and int(claim.group(1)) != expected:
                issues.append(f"{player}{label}不一致: 数据为{expected}，文中为{claim.group(1)}")

    return len(issues) == 0, issues
