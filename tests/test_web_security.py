import re
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app


def _csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, html[:500]
    return match.group(1)


def test_finish_is_post_only_and_blocks_early_finish(tmp_path):
    with TestClient(app) as client:
        login_page = client.get('/login')
        token = _csrf(login_page.text)
        response = client.post('/login', data={'identifier': '0242220005101027', 'password': 'student123', 'csrf_token': token}, follow_redirects=False)
        assert response.status_code == 303

        submit_page = client.get('/student/assignment')
        token = _csrf(submit_page.text)
        content = (
            'Overview problem solution methodology workflow features technology stack outcome conclusion. '
            'ZAS Intellect reads assignment submissions, generates AI viva questions, evaluates Bangla English answers, '
            'calculates ZAS Score, and shows teacher dashboard proctoring review. ' * 4
        )
        files = {'file': ('sample.txt', content.encode('utf-8'), 'text/plain')}
        data = {
            'course_code': 'CSE-AI-2026',
            'assignment_title': 'Security Test Submission',
            'csrf_token': token,
            'consent_ai_processing': '1',
        }
        uploaded = client.post('/student/submit', data=data, files=files, follow_redirects=False)
        assert uploaded.status_code == 303
        viva_url = uploaded.headers['location']
        session_id = int(viva_url.rstrip('/').split('/')[-1])

        assert client.get(f'/student/finish/{session_id}').status_code == 405

        viva_page = client.get(viva_url)
        token = _csrf(viva_page.text)
        early = client.post(f'/student/finish/{session_id}', data={'csrf_token': token}, follow_redirects=False)
        assert early.status_code == 303
        assert 'error=secure_not_started' in early.headers['location']


def test_complete_viva_teacher_decision_and_pdf_export():
    with TestClient(app) as client:
        token = _csrf(client.get('/login').text)
        assert client.post('/login', data={'identifier': '0242220005101473', 'password': 'student123', 'csrf_token': token}, follow_redirects=False).status_code == 303
        token = _csrf(client.get('/student/assignment').text)
        content = (
            'Problem solution methodology workflow backend frontend database testing limitation future conclusion. '
            'The system parses a submission, generates targeted AI viva questions, evaluates conceptual understanding, '
            'calculates a ZAS score, logs proctoring events, and shows teacher review dashboard. ' * 5
        )
        uploaded = client.post('/student/submit', data={
            'course_code': 'CSE-AI-2026', 'assignment_title': 'Full Workflow Test', 'group_code': 'TEST-GROUP',
            'csrf_token': token, 'consent_ai_processing': '1'
        }, files={'file': ('workflow.txt', content.encode(), 'text/plain')}, follow_redirects=False)
        assert uploaded.status_code == 303
        viva_url = uploaded.headers['location']
        session_id = int(viva_url.rstrip('/').split('/')[-1])

        start_page = client.get(f'/student/viva/{session_id}')
        start_token = _csrf(start_page.text)
        secure_start = client.post(
            f'/api/secure-start/{session_id}',
            headers={'X-CSRF-Token': start_token},
            json={'camera_ok': True, 'microphone_ok': True, 'fullscreen_ok': True, 'recording_ok': True},
        )
        assert secure_start.status_code == 200

        for _ in range(5):
            page = client.get(f'/student/viva/{session_id}')
            assert page.status_code == 200
            token = _csrf(page.text)
            qid = re.search(r'name="question_id" value="(\d+)"', page.text).group(1)
            answer = ('First the student uploads the file, then the backend parses it and generates targeted questions. '
                      'Because the teacher needs evidence of ownership, the viva answer must explain workflow, validation, limitation, and dashboard review with specific steps.')
            resp = client.post(f'/student/viva/{session_id}/answer', data={'csrf_token': token, 'question_id': qid, 'answer': answer}, follow_redirects=False)
            assert resp.status_code == 303

        result = client.get(f'/student/result/{session_id}')
        assert result.status_code == 200
        assert 'ZAS-Score Report' in result.text
        pdf = client.get(f'/student/result/{session_id}/report.pdf')
        assert pdf.status_code == 200
        assert pdf.headers['content-type'] == 'application/pdf'

        token = _csrf(result.text)
        client.post('/logout', data={'csrf_token': token}, follow_redirects=False)
        token = _csrf(client.get('/login').text)
        client.post('/login', data={'identifier': 'CIS-TEACHER', 'password': 'teacher123', 'csrf_token': token}, follow_redirects=False)
        teacher_page = client.get(f'/teacher/session/{session_id}')
        assert teacher_page.status_code == 200
        token = _csrf(teacher_page.text)
        decision = client.post(f'/teacher/session/{session_id}/decision', data={
            'csrf_token': token,
            'decision_status': 'Accepted',
            'decision_note': 'Automated workflow test accepted.'
        }, follow_redirects=False)
        assert decision.status_code == 303
