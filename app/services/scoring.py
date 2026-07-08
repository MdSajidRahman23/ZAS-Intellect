from dataclasses import dataclass


@dataclass(frozen=True)
class ScoreBreakdown:
    viva_performance: float
    submission_quality: float
    proctor_risk: float
    zas_score: float
    risk_flag: str
    summary: str


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, float(value)))


def calculate_zas_score(viva_performance: float, submission_quality: float) -> float:
    return round((clamp(viva_performance) * 0.60) + (clamp(submission_quality) * 0.40), 2)


def classify_risk(zas_score: float, proctor_risk: float = 0.0) -> str:
    if proctor_risk >= 80:
        return "Security Violation"
    if zas_score < 50:
        return "High Discrepancy"
    if proctor_risk >= 35:
        return "Proctor Review"
    if zas_score < 75:
        return "Borderline Review"
    return "Passed"


def proctor_risk_score(events: list[dict]) -> float:
    return round(clamp(sum(float(event.get("risk_weight", 0)) for event in events)), 2)


def build_score_breakdown(viva_performance: float, submission_quality: float, proctor_risk: float) -> ScoreBreakdown:
    raw_zas_score = calculate_zas_score(viva_performance, submission_quality)
    zas_score = min(raw_zas_score, 40.0) if proctor_risk >= 80 else raw_zas_score
    flag = classify_risk(zas_score, proctor_risk)
    if flag == "Security Violation":
        summary = "Critical secure-mode/proctoring violation detected. Treat as possible external assistance and require teacher decision."
    elif flag == "High Discrepancy":
        summary = "Submission quality and viva explanation do not match. Physical follow-up recommended."
    elif flag == "Proctor Review":
        summary = "Viva score is acceptable, but proctoring events require teacher review."
    elif flag == "Borderline Review":
        summary = "Student showed partial understanding. Teacher may review transcript before final decision."
    else:
        summary = "Student explanation is consistent with submission quality. No immediate follow-up required."
    return ScoreBreakdown(
        viva_performance=round(clamp(viva_performance), 2),
        submission_quality=round(clamp(submission_quality), 2),
        proctor_risk=round(clamp(proctor_risk), 2),
        zas_score=zas_score,
        risk_flag=flag,
        summary=summary,
    )
