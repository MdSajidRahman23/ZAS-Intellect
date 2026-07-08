RISK_WEIGHTS = {
    "webcam_started": 0,
    "webcam_denied": 25,
    "webcam_lost": 18,
    "face_visible": 0,
    "face_missing": 12,
    "multiple_faces": 30,
    "gaze_away": 6,
    "tab_hidden": 12,
    "tab_visible": 0,
    "copy_attempt": 8,
    "paste_attempt": 8,
    "save_attempt": 4,
    "right_click": 3,
    "inactive_60s": 6,
    "speech_started": 0,
    "speech_error": 2,
    "timer_expired": 5,
    "timer_expired_server": 0,
    "secure_mode_started": 0,
    "fullscreen_entered": 0,
    "fullscreen_exit": 100,
    "secure_mode_focus_loss": 85,
    "secure_mode_tab_hidden": 85,
    "secure_mode_terminated": 100,
    "recording_started": 0,
    "recording_chunk_saved": 0,
    "recording_failed": 18,
    "motion_normal": 0,
    "suspicious_motion": 4,
    "excessive_motion": 8,
    "long_stillness": 4,
    "audio_capture_started": 0,
}

CRITICAL_EVENTS = {
    "fullscreen_exit",
    "secure_mode_focus_loss",
    "secure_mode_tab_hidden",
    "secure_mode_terminated",
}



def risk_weight(event_type: str) -> float:
    return float(RISK_WEIGHTS.get(event_type, 1))


def event_label(event_type: str) -> str:
    labels = {
        "webcam_started": "Webcam active",
        "webcam_denied": "Webcam permission denied",
        "webcam_lost": "Webcam feed lost",
        "face_visible": "Face visible in webcam",
        "face_missing": "No face detected in webcam",
        "multiple_faces": "Multiple faces detected",
        "gaze_away": "Possible gaze-away pattern detected",
        "tab_hidden": "Student left viva tab",
        "tab_visible": "Student returned to viva tab",
        "copy_attempt": "Copy shortcut attempted",
        "paste_attempt": "Paste shortcut attempted",
        "save_attempt": "Save shortcut attempted",
        "right_click": "Right-click attempted",
        "inactive_60s": "No activity for 60 seconds",
        "speech_started": "Voice input started",
        "speech_error": "Voice input error",
        "timer_expired": "Viva timer expired",
        "timer_expired_server": "Server finalized an expired viva",
        "secure_mode_started": "Secure full-screen viva mode started",
        "fullscreen_entered": "Full-screen mode entered",
        "fullscreen_exit": "Full-screen mode was exited during viva",
        "secure_mode_focus_loss": "Viva browser window lost focus during secure mode",
        "secure_mode_tab_hidden": "Viva tab became hidden during secure mode",
        "secure_mode_terminated": "Secure mode terminated the viva automatically",
        "recording_started": "Webcam recording started",
        "recording_chunk_saved": "Video evidence chunk saved",
        "recording_failed": "Video recording failed or was blocked",
        "motion_normal": "Motion check normal",
        "suspicious_motion": "Suspicious movement pattern detected",
        "excessive_motion": "Excessive frame motion detected in webcam",
        "long_stillness": "Very low motion for an extended period",
        "audio_capture_started": "Microphone audio capture started for recording",
    }
    return labels.get(event_type, event_type.replace("_", " ").title())


def is_critical_event(event_type: str) -> bool:
    return event_type in CRITICAL_EVENTS


def integrity_recommendation(events, zas_score: float, proctor_risk: float) -> str:
    names = [getattr(e, "event_type", "") for e in events]
    critical = [name for name in names if is_critical_event(name)]
    multiple_faces = names.count("multiple_faces")
    face_missing = names.count("face_missing")
    gaze = names.count("gaze_away")
    motion = names.count("suspicious_motion") + names.count("excessive_motion")
    if critical:
        return "Critical secure-mode violation detected. Treat as possible external assistance; physical review or rejection is recommended."
    if proctor_risk >= 60 or multiple_faces:
        return "High proctoring risk. Review video timeline before accepting the viva."
    if face_missing >= 2 or gaze >= 3 or motion >= 2:
        return "Moderate proctoring risk. Student understanding may be valid, but attention/motion evidence needs teacher review."
    if zas_score >= 75 and proctor_risk < 25:
        return "Low risk. Viva answers and proctoring evidence are broadly consistent."
    return "Review recommended based on the combined ZAS score and proctor timeline."
