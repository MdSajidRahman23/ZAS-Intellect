from __future__ import annotations

DIFFICULTY_LABELS = {
    1: "Foundation",
    2: "Standard",
    3: "Advanced",
}

DIFFICULTY_NOTES = {
    1: "Foundation question: easier follow-up because the previous answer needs clearer basics.",
    2: "Standard question: normal viva difficulty for checking practical understanding.",
    3: "Advanced question: harder follow-up because the previous answer showed good understanding.",
}

DIFFICULTY_SCORE_CAPS = {
    1: 75.0,
    2: 90.0,
    3: 100.0,
}

DIFFICULTY_MULTIPLIERS = {
    1: 0.85,
    2: 1.00,
    3: 1.12,
}


def normalize_difficulty(level: int | float | str | None) -> int:
    try:
        value = int(level or 2)
    except Exception:
        value = 2
    return max(1, min(3, value))


def difficulty_label(level: int | float | str | None) -> str:
    return DIFFICULTY_LABELS.get(normalize_difficulty(level), "Standard")


def difficulty_note(level: int | float | str | None) -> str:
    return DIFFICULTY_NOTES.get(normalize_difficulty(level), DIFFICULTY_NOTES[2])


def next_difficulty_level(
    previous_raw_score: float,
    current_level: int | float | str | None,
    raise_threshold: int = 75,
    lower_threshold: int = 50,
) -> int:
    """Adaptive rule: good answer => harder next question; weak answer => easier next question."""
    level = normalize_difficulty(current_level)
    try:
        score = float(previous_raw_score)
    except Exception:
        score = 0.0
    if score >= raise_threshold:
        return min(3, level + 1)
    if score < lower_threshold:
        return max(1, level - 1)
    return level


def adjusted_answer_score(raw_score: float, difficulty_level: int | float | str | None) -> float:
    """Convert examiner score into official mark using adaptive difficulty.

    Foundation questions are easier, so their maximum official mark is capped.
    Advanced questions are harder, so strong answers receive a small difficulty bonus.
    """
    level = normalize_difficulty(difficulty_level)
    try:
        raw = max(0.0, min(100.0, float(raw_score)))
    except Exception:
        raw = 0.0
    weighted = raw * DIFFICULTY_MULTIPLIERS[level]
    capped = min(weighted, DIFFICULTY_SCORE_CAPS[level])
    return round(max(0.0, min(100.0, capped)), 2)
