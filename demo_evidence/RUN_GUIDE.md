\# Demo Run Guide



\## Setup



cd "D:\\ZAS-Intellect"

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

.\\scripts\\setup\_windows.ps1



\## Start Server



.\\.venv\\Scripts\\Activate.ps1

python -m uvicorn app.main:app --reload --log-level debug



Open:



http://127.0.0.1:8000



\## Recommended Demo Environment



AI\_PROVIDER=offline

MAX\_UPLOAD\_MB=50



ZAS-Intellect supports Grok/xAI, Gemini, and Offline fallback. If external providers fail due to quota, credit, license, or network issues, the system safely continues in offline mode.



\## Demo Flow



1\. Login as student.

2\. Submit assignment file.

3\. Start secure viva.

4\. Allow camera and microphone.

5\. Answer one or more viva questions.

6\. Click Finish Viva.

7\. View ZAS result.

8\. Teacher reviews score, transcript, proctoring events, and video evidence.



\## Evidence



Demo evidence is available in:



app/data/uploads/

app/data/recordings/

demo\_evidence/



\## Ethics Note



ZAS-Intellect is a teacher decision-support system. It preserves reviewable evidence but does not automatically punish students. Final academic decision remains with the teacher.

