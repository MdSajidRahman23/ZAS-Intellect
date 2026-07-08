from app.services.scoring import calculate_zas_score, classify_risk, build_score_breakdown


def test_zas_formula():
    assert calculate_zas_score(80, 90) == 84.0
    assert calculate_zas_score(40, 80) == 56.0


def test_flags():
    assert classify_risk(49) == "High Discrepancy"
    assert classify_risk(70) == "Borderline Review"
    assert classify_risk(80, 40) == "Proctor Review"
    assert classify_risk(90, 5) == "Passed"


def test_breakdown():
    b = build_score_breakdown(50, 50, 0)
    assert b.zas_score == 50.0
    assert b.risk_flag == "Borderline Review"

from app.services.reporting import _csv_safe


def test_csv_sanitizes_formula_injection():
    assert _csv_safe("=cmd|' /C calc'!A0").startswith("'")
    assert _csv_safe(" \n+SUM(1,1)").startswith("'")
    assert "\n" not in _csv_safe("hello\nworld")


def test_adaptive_difficulty_rules_and_marking():
    from app.services.adaptive import adjusted_answer_score, next_difficulty_level

    assert next_difficulty_level(82, 2) == 3
    assert next_difficulty_level(65, 2) == 2
    assert next_difficulty_level(35, 2) == 1
    assert adjusted_answer_score(95, 1) <= 75
    assert adjusted_answer_score(80, 3) > 80
