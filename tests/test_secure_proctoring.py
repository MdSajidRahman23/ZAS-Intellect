import re
from fastapi.testclient import TestClient

from app.main import app


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def _create_viva(client: TestClient) -> tuple[int, str]:
    token = _csrf(client.get('/login').text)
    response = client.post('/login', data={'identifier': '0242220005101027', 'password': 'student123', 'csrf_token': token}, follow_redirects=False)
    assert response.status_code == 303
    token = _csrf(client.get('/student/assignment').text)
    content = (
        'Secure proctoring proposal with AI viva, webcam evidence, fullscreen protection, motion detection, '
        'teacher dashboard, and ZAS Score integrity reporting. ' * 6
    )
    uploaded = client.post('/student/submit', data={
        'course_code': 'CSE-AI-2026', 'assignment_title': 'Secure Proctor Test',
        'csrf_token': token, 'consent_ai_processing': '1'
    }, files={'file': ('secure.txt', content.encode('utf-8'), 'text/plain')}, follow_redirects=False)
    assert uploaded.status_code == 303
    session_id = int(uploaded.headers['location'].rstrip('/').split('/')[-1])
    page = client.get(f'/student/viva/{session_id}')
    assert page.status_code == 200
    return session_id, _csrf(page.text)


def test_secure_terminate_caps_score_and_flags_session():
    with TestClient(app) as client:
        session_id, token = _create_viva(client)
        client.post(
            f'/api/secure-start/{session_id}',
            headers={'X-CSRF-Token': token},
            json={'camera_ok': True, 'microphone_ok': True, 'fullscreen_ok': True, 'recording_ok': True},
        )
        response = client.post(
            f'/api/secure-terminate/{session_id}',
            headers={'X-CSRF-Token': token},
            json={'event_type': 'fullscreen_exit', 'details': 'ESC/fullscreen exit during test'},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload['status'] == 'terminated'
        result = client.get(payload['redirect_url'])
        assert result.status_code == 200
        assert 'Security Violation' in result.text


def test_recording_chunk_upload_and_teacher_playback_route():
    with TestClient(app) as client:
        session_id, token = _create_viva(client)
        secure_start = client.post(
            f'/api/secure-start/{session_id}',
            headers={'X-CSRF-Token': token},
            json={'camera_ok': True, 'microphone_ok': True, 'fullscreen_ok': True, 'recording_ok': True},
        )
        assert secure_start.status_code == 200
        video_bytes = b'\x1a\x45\xdf\xa3 fake-webm-data-for-test'
        uploaded = client.post(
            f'/api/recording/{session_id}',
            headers={'X-CSRF-Token': token},
            data={'chunk_index': '0', 'duration_ms': '10000'},
            files={'video': ('chunk.webm', video_bytes, 'video/webm')},
        )
        assert uploaded.status_code == 200
        chunk_id = uploaded.json()['chunk_id']
        client.post(f'/api/secure-terminate/{session_id}', headers={'X-CSRF-Token': token}, json={'event_type': 'fullscreen_exit'})

        # Teacher can review the saved evidence.
        token = _csrf(client.get(f'/student/result/{session_id}').text)
        client.post('/logout', data={'csrf_token': token}, follow_redirects=False)
        token = _csrf(client.get('/login').text)
        client.post('/login', data={'identifier': 'CIS-TEACHER', 'password': 'teacher123', 'csrf_token': token}, follow_redirects=False)
        detail = client.get(f'/teacher/session/{session_id}')
        assert detail.status_code == 200
        assert 'Video Recording Evidence' in detail.text
        playback = client.get(f'/teacher/session/{session_id}/video/{chunk_id}')
        assert playback.status_code == 200
        assert playback.content == video_bytes


def test_viva_is_locked_and_timer_not_started_before_secure_start():
    with TestClient(app) as client:
        session_id, token = _create_viva(client)
        page = client.get(f'/student/viva/{session_id}')
        assert page.status_code == 200
        assert 'Question locked until secure start' in page.text
        assert 'Not started' in page.text
        qid = re.search(r'name="question_id" value="(\d+)"', page.text).group(1)
        blocked = client.post(
            f'/student/viva/{session_id}/answer',
            data={'csrf_token': token, 'question_id': qid, 'answer': 'This answer should be blocked because secure mode has not started yet.'},
            follow_redirects=False,
        )
        assert blocked.status_code == 303
        assert 'error=secure_not_started' in blocked.headers['location']


def test_secure_start_rejects_missing_microphone():
    with TestClient(app) as client:
        session_id, token = _create_viva(client)
        rejected = client.post(
            f'/api/secure-start/{session_id}',
            headers={'X-CSRF-Token': token},
            json={'camera_ok': True, 'microphone_ok': False, 'fullscreen_ok': True, 'recording_ok': True},
        )
        assert rejected.status_code == 409
        assert 'microphone' in rejected.text.lower()
