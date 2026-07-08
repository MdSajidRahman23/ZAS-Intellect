(function () {
  const shell = document.querySelector('.viva-shell');
  if (!shell) return;

  const sessionId = shell.dataset.sessionId;
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const mediaPipeEnabled = shell.dataset.mediapipeEnabled === '1';
  const secureFullscreen = shell.dataset.secureFullscreen === '1';
  const endOnFullscreenExit = shell.dataset.endOnFullscreenExit === '1';
  const endOnFocusLoss = shell.dataset.endOnFocusLoss === '1';
  const videoRecordingEnabled = shell.dataset.videoRecording === '1';
  const videoChunkSeconds = Math.max(3, Number(shell.dataset.videoChunkSeconds || 10));
  const motionEnabled = shell.dataset.motionEnabled === '1';
  const motionInterval = Math.max(1000, Number(shell.dataset.motionIntervalMs || 2500));
  const serverSecureStarted = shell.dataset.secureStarted === '1';

  const statusEl = document.getElementById('proctorStatus');
  const recordingStatus = document.getElementById('recordingStatus');
  const motionStatus = document.getElementById('motionStatus');
  const video = document.getElementById('webcam');
  const cameraPreviewFrame = document.getElementById('cameraPreviewFrame');
  const cameraPreviewBadge = document.getElementById('cameraPreviewBadge');
  const cameraPreviewOverlay = document.getElementById('cameraPreviewOverlay');
  const answerBox = document.getElementById('answerBox');
  const answerForm = document.getElementById('answerForm');
  const answerErrorBox = document.getElementById('answerErrorBox');
  const answerSubmitBtn = answerForm ? answerForm.querySelector('button[type="submit"]') : null;
  const questionIdInput = document.getElementById('questionIdInput');
  const questionMeta = document.getElementById('questionMeta');
  const questionText = document.getElementById('questionText');
  const adaptiveHint = document.getElementById('adaptiveHint');
  const questionCrumb = document.getElementById('vivaQuestionCrumb');
  const progressFill = document.getElementById('vivaProgressFill');
  const voiceBtn = document.getElementById('voiceBtn');
  const voiceLanguage = document.getElementById('voiceLanguage');
  const timerEl = document.getElementById('vivaTimer');
  const miniTimer = document.getElementById('miniTimer');
  const startOverlay = document.getElementById('secureStartOverlay');
  const startBtn = document.getElementById('startSecureBtn');
  const secureConsent = document.getElementById('secureConsent');
  const secureBanner = document.getElementById('secureLiveBanner');
  const permissionStatus = document.getElementById('permissionStatus');
  const protectedContent = document.getElementById('protectedVivaContent');
  const lockedPlaceholder = document.getElementById('lockedQuestionPlaceholder');

  let remaining = Number(shell.dataset.remainingSeconds || 0);
  let timerRunning = serverSecureStarted;
  let timeoutSubmitted = false;
  let secureStarted = false;
  let secureStarting = false;
  let terminating = false;
  let normalSubmit = false;
  let graceUntil = 0;
  let mediaStream = null;
  let mediaRecorder = null;
  let chunkIndex = 0;
  let lastFaceEvent = { type: '', at: 0 };
  let lastMotionLogAt = 0;
  let stillCount = 0;
  let previousFrame = null;
  let pendingUploads = [];
  let stopRecordingPromise = null;
  let cameraStarted = false;
  let recordingStarted = false;
  let fullscreenStarted = false;
  let startupStage = 'idle';

  setCameraPreview('Camera preview locked', 'waiting');
  if (video) {
    video.addEventListener('loadedmetadata', () => setCameraPreview('Live camera preview', 'live'));
    video.addEventListener('playing', () => setCameraPreview('Live camera preview', 'live'));
    video.addEventListener('pause', () => { if (!secureStarted) setCameraPreview('Camera preview paused', 'waiting'); });
  }

  function setStatus(text) { if (statusEl) statusEl.textContent = text; }
  function setRecording(text) { if (recordingStatus) recordingStatus.textContent = text; }
  function setMotion(text) { if (motionStatus) motionStatus.textContent = text; }
  function setCameraPreview(text, state) {
    if (cameraPreviewBadge) cameraPreviewBadge.textContent = text || 'Camera preview';
    if (cameraPreviewFrame) {
      cameraPreviewFrame.classList.remove('camera-live', 'camera-error', 'camera-waiting');
      if (state) cameraPreviewFrame.classList.add(`camera-${state}`);
    }
    if (cameraPreviewOverlay) cameraPreviewOverlay.setAttribute('aria-label', text || 'Camera preview');
  }

  function setPermission(text, kind) {
    if (!permissionStatus) return;
    permissionStatus.textContent = text;
    permissionStatus.className = `permission-status ${kind || 'info'}`;
  }

  function hasFullscreenElement() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement);
  }

  function hasLiveVideoTrack() {
    return !!(mediaStream && mediaStream.getVideoTracks().some((track) => track.readyState === 'live'));
  }

  function hasLiveAudioTrack() {
    return !!(mediaStream && mediaStream.getAudioTracks().some((track) => track.readyState === 'live'));
  }

  async function logEvent(event_type, details) {
    try {
      await fetch(`/api/proctor/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ event_type, details: details || event_type }),
        keepalive: true
      });
    } catch (e) {
      console.warn('proctor log failed', e);
    }
  }

  async function notifySecureStart() {
    const payload = {
      camera_ok: hasLiveVideoTrack(),
      microphone_ok: hasLiveAudioTrack(),
      fullscreen_ok: !secureFullscreen || hasFullscreenElement(),
      recording_ok: !videoRecordingEnabled || recordingStarted
    };
    const res = await fetch(`/api/secure-start/${sessionId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify(payload)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.ok) {
      throw new Error(data.detail || 'Secure start was rejected. Camera, microphone, recording, and full-screen are mandatory.');
    }
    if (typeof data.remaining_seconds === 'number') {
      remaining = data.remaining_seconds;
    }
    timerRunning = true;
    updateTimer();
  }

  async function stopRecording(flush = false) {
    if (stopRecordingPromise) return stopRecordingPromise;

    stopRecordingPromise = new Promise((resolve) => {
      const finish = async () => {
        if (mediaStream) {
          for (const track of mediaStream.getTracks()) {
            try { track.stop(); } catch (e) { /* ignore */ }
          }
        }
        try { await Promise.race([
          Promise.allSettled(pendingUploads),
          new Promise((r) => setTimeout(r, flush ? 3500 : 700))
        ]); } catch (e) { /* ignore */ }
        setRecording('Stopped');
        setCameraPreview('Camera stopped', 'waiting');
        resolve();
      };

      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.addEventListener('stop', finish, { once: true });
        try { mediaRecorder.requestData(); } catch (e) { /* ignore */ }
        try { mediaRecorder.stop(); } catch (e) { finish(); }
      } else {
        finish();
      }
    });
    return stopRecordingPromise;
  }

  async function secureTerminate(event_type, details) {
    if (terminating || normalSubmit) return;
    terminating = true;
    setStatus('Secure-mode violation detected. Viva is ending...');
    if (secureBanner) secureBanner.textContent = 'Secure-mode violation detected. Exam ended.';
    try { await stopRecording(true); } catch (e) { /* ignore */ }
    try {
      const res = await fetch(`/api/secure-terminate/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ event_type, details }),
        keepalive: true
      });
      const payload = await res.json().catch(() => ({}));
      window.location.replace(payload.redirect_url || `/student/result/${sessionId}`);
    } catch (e) {
      window.location.replace(`/student/result/${sessionId}`);
    }
  }

  function throttledFaceEvent(event_type, details, gapMs = 15000) {
    const now = Date.now();
    if (lastFaceEvent.type === event_type && now - lastFaceEvent.at < gapMs) return;
    lastFaceEvent = { type: event_type, at: now };
    logEvent(event_type, details);
  }

  function fmt(seconds) {
    seconds = Math.max(0, Number(seconds || 0));
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${String(s).padStart(2, '0')}`;
  }

  function updateTimer() {
    if (!timerRunning) {
      if (timerEl) {
        timerEl.textContent = 'Not started';
        timerEl.classList.add('waiting');
      }
      if (miniTimer) miniTimer.textContent = 'Not started';
      return;
    }
    if (timerEl) {
      timerEl.textContent = fmt(remaining);
      timerEl.classList.remove('waiting');
    }
    if (miniTimer) miniTimer.textContent = fmt(remaining);
    if (remaining <= 60 && timerEl) timerEl.classList.add('danger');
    if (remaining <= 0 && !timeoutSubmitted) {
      timeoutSubmitted = true;
      normalSubmit = true;
      logEvent('timer_expired', 'Viva timer expired; auto-finishing session');
      stopRecording(true).finally(() => {
        const finishForm = document.querySelector('form[action^="/student/finish/"]');
        if (finishForm) finishForm.submit();
      });
    }
  }

  updateTimer();
  setInterval(() => {
    if (!timerRunning || terminating || normalSubmit) return;
    remaining -= 1;
    updateTimer();
  }, 1000);

  function enableVivaControls() {
    shell.classList.remove('secure-locked');
    if (startOverlay) startOverlay.classList.add('hidden');
    if (protectedContent) protectedContent.setAttribute('aria-hidden', 'false');
    if (lockedPlaceholder) lockedPlaceholder.style.display = 'none';
    if (secureBanner) secureBanner.textContent = 'Secure mode active: live camera preview + recording + motion checks';
    document.querySelectorAll('.protected-viva-content textarea[disabled], .protected-viva-content select[disabled], .protected-viva-content button[disabled], .finish-box button[disabled]').forEach((el) => {
      el.disabled = false;
      el.classList.remove('secure-disabled');
    });
  }

  async function enterFullscreen() {
    if (!secureFullscreen) {
      fullscreenStarted = true;
      return;
    }
    const target = document.documentElement;
    const fn = target.requestFullscreen || target.webkitRequestFullscreen || target.msRequestFullscreen;
    if (!fn) throw new Error('Fullscreen API is not supported by this browser. Use updated Chrome or Edge.');
    await fn.call(target);
    fullscreenStarted = true;
    await logEvent('fullscreen_entered', 'Student entered full-screen secure viva mode');
  }

  function explainMediaError(e) {
    if (!window.isSecureContext) {
      return 'Camera/microphone needs a secure browser context. Open http://127.0.0.1:8000 or http://localhost:8000, not a file path or LAN/IP URL.';
    }
    const name = e && e.name ? e.name : '';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      return 'Camera/microphone permission was blocked. Click the lock/camera icon beside the address bar, allow Camera and Microphone, then reload.';
    }
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      return 'No camera or microphone was found. A webcam and microphone are mandatory for secure viva.';
    }
    if (name === 'NotReadableError' || name === 'TrackStartError') {
      return 'Camera/microphone is busy in another app. Close Zoom/Meet/Teams/Camera app, then try again.';
    }
    if (name === 'OverconstrainedError') {
      return 'Camera/microphone constraints could not be satisfied. Connect a working webcam and microphone, then reload.';
    }
    return e && e.message ? e.message : 'Camera/microphone could not start.';
  }

  async function requestCameraAndMic() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error('Webcam API not supported. Use updated Chrome or Edge.');
    }
    if (!window.isSecureContext) {
      throw new Error('Camera/microphone permission requires http://127.0.0.1:8000 or http://localhost:8000.');
    }
    setPermission('Browser permission prompt should appear now. You must allow both Camera and Microphone.', 'warn');
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' },
      audio: { echoCancellation: true, noiseSuppression: true }
    });
    if (!hasLiveVideoTrack()) {
      throw new Error('Camera is required. No live video track was detected.');
    }
    if (!hasLiveAudioTrack()) {
      throw new Error('Microphone is required. No live audio track was detected.');
    }
    cameraStarted = true;
    if (video) {
      setCameraPreview('Connecting live camera...', 'waiting');
      video.srcObject = mediaStream;
      video.muted = true;
      video.playsInline = true;
      await new Promise((resolve) => {
        if (video.readyState >= 1) return resolve();
        video.addEventListener('loadedmetadata', resolve, { once: true });
        setTimeout(resolve, 1200);
      });
      await video.play().catch(() => {});
      if (video.videoWidth > 0 || video.readyState >= 2) {
        setCameraPreview('Live camera preview', 'live');
      } else {
        setCameraPreview('Camera connected; waiting for frame', 'waiting');
      }
    }
    setStatus('Live camera preview and microphone ready. Stay alone and visible.');
    setPermission('Camera and microphone permission granted. Now entering full-screen secure mode.', 'ok');
    await logEvent('webcam_started', 'Webcam permission granted');
    await logEvent('audio_capture_started', 'Microphone capture started for video evidence');
  }

  async function startMediaPipeFaceChecks() {
    if (!mediaPipeEnabled || !window.FaceMesh || !video) return;
    try {
      const faceMesh = new window.FaceMesh({ locateFile: (file) => `https://cdn.jsdelivr.net/npm/@mediapipe/face_mesh/${file}` });
      faceMesh.setOptions({ maxNumFaces: 2, refineLandmarks: true, minDetectionConfidence: 0.55, minTrackingConfidence: 0.55 });
      faceMesh.onResults((results) => {
        const faces = results.multiFaceLandmarks || [];
        if (!faces.length) {
          throttledFaceEvent('face_missing', 'MediaPipe did not detect a face in the webcam frame');
          setStatus('Webcam active, but face is not clearly visible.');
          return;
        }
        if (faces.length > 1) {
          throttledFaceEvent('multiple_faces', 'MediaPipe detected more than one face');
          setStatus('Multiple faces detected. Stay alone during viva.');
          return;
        }
        const lm = faces[0];
        const nose = lm[1];
        const leftEye = lm[33];
        const rightEye = lm[263];
        const eyeCenterX = (leftEye.x + rightEye.x) / 2;
        const gazeOffset = Math.abs(nose.x - eyeCenterX);
        if (gazeOffset > 0.065 || nose.x < 0.28 || nose.x > 0.72) {
          throttledFaceEvent('gaze_away', 'Possible repeated gaze-away or head-turn pattern detected');
          setStatus('Face visible. Please look at the screen while answering.');
        } else {
          throttledFaceEvent('face_visible', 'Single face visible in webcam frame', 45000);
          setStatus('Webcam, face, and secure checks active.');
        }
      });
      setInterval(async () => {
        if (video.readyState >= 2 && secureStarted && !terminating) {
          try { await faceMesh.send({ image: video }); } catch (e) { /* skip frame */ }
        }
      }, 900);
      await logEvent('face_visible', 'MediaPipe face proctoring initialized');
    } catch (e) {
      console.warn('MediaPipe unavailable', e);
      await logEvent('recording_failed', 'MediaPipe proctoring could not initialize; webcam recording continues');
    }
  }

  function startMotionDetection() {
    if (!motionEnabled || !video) return;
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    canvas.width = 160;
    canvas.height = 120;
    setMotion('Active');
    setInterval(() => {
      if (!secureStarted || terminating || video.readyState < 2) return;
      try {
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        const frame = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        if (!previousFrame) {
          previousFrame = new Uint8ClampedArray(frame);
          return;
        }
        let changed = 0;
        const total = canvas.width * canvas.height;
        for (let i = 0; i < frame.length; i += 16) {
          const diff = Math.abs(frame[i] - previousFrame[i]) + Math.abs(frame[i + 1] - previousFrame[i + 1]) + Math.abs(frame[i + 2] - previousFrame[i + 2]);
          if (diff > 85) changed += 4;
        }
        previousFrame = new Uint8ClampedArray(frame);
        const ratio = changed / total;
        const now = Date.now();
        if (ratio > 0.22 && now - lastMotionLogAt > 12000) {
          lastMotionLogAt = now;
          stillCount = 0;
          setMotion('High motion');
          logEvent('excessive_motion', `Large frame motion detected: ${(ratio * 100).toFixed(1)}% changed`);
        } else if (ratio > 0.10 && now - lastMotionLogAt > 15000) {
          lastMotionLogAt = now;
          stillCount = 0;
          setMotion('Suspicious');
          logEvent('suspicious_motion', `Suspicious frame motion detected: ${(ratio * 100).toFixed(1)}% changed`);
        } else if (ratio < 0.003) {
          stillCount += 1;
          if (stillCount >= 8 && now - lastMotionLogAt > 20000) {
            lastMotionLogAt = now;
            setMotion('Very still');
            logEvent('long_stillness', 'Very low webcam motion for an extended period');
          }
        } else {
          stillCount = 0;
          setMotion('Normal');
        }
      } catch (e) {
        console.warn('motion check failed', e);
      }
    }, motionInterval);
  }

  async function uploadRecordingChunk(blob, durationMs) {
    if (!blob || !blob.size) return;
    const form = new FormData();
    form.append('chunk_index', String(chunkIndex++));
    form.append('duration_ms', String(durationMs || videoChunkSeconds * 1000));
    form.append('video', blob, `zas_session_${sessionId}_${Date.now()}.webm`);
    const p = fetch(`/api/recording/${sessionId}`, {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
      body: form,
      keepalive: false
    }).then((res) => {
      if (res.ok) setRecording(`Saved #${chunkIndex}`);
      else setRecording('Upload failed');
    }).catch((e) => {
      console.warn('recording upload failed', e);
      setRecording('Upload failed');
    });
    pendingUploads.push(p);
    await p;
  }

  async function startRecording(stream) {
    stopRecordingPromise = null;
    if (!videoRecordingEnabled) {
      recordingStarted = true;
      setRecording('Disabled');
      return;
    }
    if (!window.MediaRecorder) {
      throw new Error('Video recording is required, but this browser does not support MediaRecorder. Use updated Chrome or Edge.');
    }
    const preferred = 'video/webm;codecs=vp8,opus';
    const options = MediaRecorder.isTypeSupported(preferred) ? { mimeType: preferred } : { mimeType: 'video/webm' };
    try {
      mediaRecorder = new MediaRecorder(stream, options);
    } catch (e) {
      throw new Error(e.message || 'Video recording could not initialize.');
    }
    mediaRecorder.ondataavailable = (event) => uploadRecordingChunk(event.data, videoChunkSeconds * 1000);
    mediaRecorder.onerror = (event) => {
      recordingStarted = false;
      logEvent('recording_failed', event.error?.message || 'MediaRecorder error');
    };
    mediaRecorder.start(videoChunkSeconds * 1000);
    if (mediaRecorder.state !== 'recording') {
      throw new Error('Video recording did not start. Camera/microphone evidence is mandatory.');
    }
    recordingStarted = true;
    setRecording('Recording');
    await logEvent('recording_started', 'Webcam/microphone recording started for viva evidence');
  }

  async function finalizeSecureStartup() {
    await startRecording(mediaStream);
    await notifySecureStart();
    secureStarted = true;
    secureStarting = false;
    graceUntil = Date.now() + 3000;
    enableVivaControls();
    await startMediaPipeFaceChecks();
    startMotionDetection();

    const [track] = mediaStream.getVideoTracks();
    setInterval(() => {
      if (secureStarted && (!track || track.readyState !== 'live')) {
        logEvent('webcam_lost', 'Video track stopped or unavailable');
        setStatus('Webcam feed appears inactive.');
      }
    }, 20000);
  }

  if (secureConsent && startBtn) {
    secureConsent.addEventListener('change', () => { startBtn.disabled = !secureConsent.checked; });
  }

  async function startSecureMode() {
    if (secureStarted || secureStarting) return;
    if (!secureConsent?.checked && secureFullscreen) return;
    secureStarting = true;
    startupStage = cameraStarted ? 'fullscreen' : 'media';
    if (startBtn) {
      startBtn.disabled = true;
      startBtn.textContent = cameraStarted ? 'Entering Full Screen...' : 'Requesting Camera & Microphone...';
    }
    setStatus('Starting secure mode...');

    try {
      if (!cameraStarted) {
        await requestCameraAndMic();
      }

      if (!fullscreenStarted) {
        if (startBtn) startBtn.textContent = 'Entering Full Screen...';
        try {
          await enterFullscreen();
        } catch (fsError) {
          secureStarting = false;
          startupStage = 'fullscreen';
          setPermission('Camera/mic is ready. Click the button once more to enter full-screen and start the viva.', 'warn');
          setStatus('Camera ready. Full-screen needs one more click.');
          if (startBtn) {
            startBtn.disabled = false;
            startBtn.textContent = 'Enter Full Screen & Start Viva';
          }
          return;
        }
      }

      await finalizeSecureStartup();
    } catch (e) {
      secureStarting = false;
      const message = explainMediaError(e);
      if (startBtn) {
        startBtn.disabled = false;
        startBtn.textContent = startupStage === 'fullscreen' ? 'Enter Full Screen & Start Viva' : 'Start Secure Viva';
      }
      setStatus(message);
      setPermission(message, 'error');
      setCameraPreview('Camera/microphone blocked', 'error');
      try { await logEvent('secure_start_blocked', message); } catch (_) { /* ignore */ }
      try { await stopRecording(false); } catch (_) { /* ignore */ }
      mediaStream = null;
      mediaRecorder = null;
      cameraStarted = false;
      recordingStarted = false;
      stopRecordingPromise = null;
      fullscreenStarted = hasFullscreenElement();
    }
  }

  if (startBtn) startBtn.addEventListener('click', startSecureMode);
  if (!secureFullscreen && startOverlay) startSecureMode();

  function showAnswerError(message) {
    if (!answerErrorBox) return;
    answerErrorBox.textContent = message || 'Answer could not be submitted. Please try again.';
    answerErrorBox.classList.remove('hidden');
  }

  function hideAnswerError() {
    if (!answerErrorBox) return;
    answerErrorBox.textContent = '';
    answerErrorBox.classList.add('hidden');
  }

  function setAnswerSubmitting(isSubmitting) {
    if (!answerSubmitBtn) return;
    answerSubmitBtn.disabled = !!isSubmitting;
    answerSubmitBtn.textContent = isSubmitting ? 'Saving Answer...' : 'Submit Answer';
  }

  function updateQuestionProgress(answered, total, nextQuestionExists) {
    const safeTotal = Math.max(1, Number(total || 1));
    const safeAnswered = Math.max(0, Number(answered || 0));
    if (progressFill) progressFill.style.width = `${Math.min(100, Math.round((safeAnswered / safeTotal) * 100))}%`;
    if (questionCrumb) {
      const nextIndex = nextQuestionExists ? safeAnswered + 1 : safeAnswered;
      questionCrumb.textContent = `Question ${nextIndex} of ${safeTotal}`;
    }
  }

  function loadNextQuestion(payload) {
    const next = payload.next_question;
    if (!next) return;
    if (questionIdInput) questionIdInput.value = next.id;
    if (questionMeta) questionMeta.textContent = `${next.category} question · Level: ${next.difficulty_label || 'Standard'} · Provider: ${next.provider || 'OFFLINE'}`;
    if (questionText) questionText.textContent = next.question;
    if (adaptiveHint) adaptiveHint.textContent = next.adaptive_note || 'Adaptive viva question based on previous performance.';
    if (answerBox) {
      answerBox.value = '';
      answerBox.focus({ preventScroll: true });
    }
    if (typeof payload.remaining_seconds === 'number') {
      remaining = payload.remaining_seconds;
      updateTimer();
    }
    updateQuestionProgress(payload.answered, payload.total, true);
    setStatus(payload.adaptive_message || 'Answer saved. Next adaptive question loaded without restarting camera/microphone.');
    setPermission('Secure session is still active. Difficulty is adjusted from your previous answer. No new camera/microphone permission is needed.', 'ok');
  }

  if (answerForm) {
    answerForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (terminating || normalSubmit) return;
      hideAnswerError();
      const answerText = (answerBox?.value || '').trim();
      if (answerText.length < 20) {
        showAnswerError('Your answer is too short. Please explain the logic, steps, and decision clearly.');
        return;
      }
      setAnswerSubmitting(true);
      try {
        const response = await fetch(answerForm.action, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' },
          body: new FormData(answerForm)
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) {
          showAnswerError(payload.message || 'Answer could not be submitted. Please try again.');
          return;
        }
        if (payload.completed && payload.redirect_url) {
          normalSubmit = true;
          setStatus(payload.message || 'All answers saved. Opening result report...');
          setPermission('All answers saved. Recording is being finalized before the report opens.', 'ok');
          await stopRecording(true);
          window.location.replace(payload.redirect_url);
          return;
        }
        loadNextQuestion(payload);
      } catch (e) {
        showAnswerError(e.message || 'Network error while submitting answer. Please try again.');
      } finally {
        if (!normalSubmit) setAnswerSubmitting(false);
      }
    });
  }

  document.querySelectorAll('form').forEach((form) => {
    form.addEventListener('submit', () => {
      if (form.id === 'answerForm') return;
      normalSubmit = true;
      try { stopRecording(false); } catch (e) { /* ignore */ }
    });
  });

  function handleFullscreenExit(reason) {
    if (!secureStarted || normalSubmit || terminating || Date.now() < graceUntil) return;
    if (endOnFullscreenExit && !hasFullscreenElement()) {
      secureTerminate('fullscreen_exit', reason || 'Student exited full-screen mode during secure viva. ESC/F11/fullscreen exit is treated as possible external assistance.');
    }
  }

  ['fullscreenchange', 'webkitfullscreenchange', 'msfullscreenchange'].forEach((evt) => {
    document.addEventListener(evt, () => handleFullscreenExit('Full-screen state changed; no full-screen element remains.'));
  });

  setInterval(() => {
    if (secureStarted && endOnFullscreenExit && !normalSubmit && !terminating && Date.now() >= graceUntil && !hasFullscreenElement()) {
      secureTerminate('fullscreen_exit', 'Full-screen heartbeat detected that the protected viva screen was exited.');
    }
  }, 600);

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      if (secureStarted && endOnFocusLoss && !normalSubmit && Date.now() >= graceUntil) {
        secureTerminate('secure_mode_tab_hidden', 'Student left or hid the viva tab during secure mode.');
      } else if (secureStarted) {
        logEvent('tab_hidden', 'Student left viva tab');
      }
    } else if (secureStarted) {
      logEvent('tab_visible', 'Student returned to viva tab');
    }
  });

  window.addEventListener('blur', () => {
    if (secureStarted && endOnFocusLoss && !normalSubmit && !terminating && Date.now() >= graceUntil) {
      setTimeout(() => {
        if (!document.hasFocus() && !normalSubmit && !terminating) {
          secureTerminate('secure_mode_focus_loss', 'Viva browser window lost focus during secure mode.');
        }
      }, 700);
    }
  });

  window.addEventListener('pagehide', () => {
    if (secureStarted && !normalSubmit && !terminating) {
      secureTerminate('secure_mode_page_unload', 'Student attempted to close, reload, or navigate away from the secure viva page.');
    }
  });

  document.addEventListener('keydown', (e) => {
    const key = e.key.toLowerCase();
    if (key === 'escape' && secureStarted && endOnFullscreenExit && !normalSubmit && !terminating) {
      logEvent('fullscreen_exit', 'ESC key was pressed during secure full-screen viva.');
      setTimeout(() => handleFullscreenExit('ESC key exited full-screen mode during secure viva.'), 150);
      setTimeout(() => {
        if (!terminating && !normalSubmit) secureTerminate('fullscreen_exit', 'ESC key was pressed during secure full-screen viva.');
      }, 650);
    }
    if ((e.ctrlKey || e.metaKey) && key === 'c') logEvent('copy_attempt', 'Copy shortcut attempted');
    if ((e.ctrlKey || e.metaKey) && key === 'v') logEvent('paste_attempt', 'Paste shortcut attempted');
    if ((e.ctrlKey || e.metaKey) && key === 's') logEvent('save_attempt', 'Save shortcut attempted');
  });

  document.addEventListener('paste', () => logEvent('paste_attempt', 'Paste event fired inside viva'));
  document.addEventListener('contextmenu', (e) => { e.preventDefault(); logEvent('right_click', 'Right click attempted'); });

  let lastActivity = Date.now();
  ['mousemove', 'keydown', 'click', 'input', 'touchstart'].forEach(evt => document.addEventListener(evt, () => lastActivity = Date.now()));
  setInterval(() => {
    if (secureStarted && Date.now() - lastActivity > 60000) {
      logEvent('inactive_60s', 'No keyboard/mouse activity for 60 seconds');
      lastActivity = Date.now();
    }
  }, 15000);

  if (voiceBtn && answerBox) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      voiceBtn.disabled = true;
      voiceBtn.textContent = 'Voice Not Supported';
    } else {
      let recognition = null;
      let listening = false;
      let finalTranscript = '';

      function buildRecognition() {
        const rec = new SpeechRecognition();
        rec.continuous = true;
        rec.interimResults = true;
        rec.lang = voiceLanguage ? voiceLanguage.value : 'bn-BD';
        rec.onresult = (event) => {
          let interim = '';
          for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = event.results[i][0].transcript;
            if (event.results[i].isFinal) finalTranscript += transcript + ' ';
            else interim += transcript;
          }
          answerBox.value = finalTranscript + interim;
        };
        rec.onerror = (event) => logEvent('speech_error', event.error || 'Speech recognition error');
        rec.onend = () => {
          if (listening) {
            try { rec.start(); } catch (e) { /* ignore duplicate start */ }
          }
        };
        return rec;
      }

      voiceBtn.addEventListener('click', async () => {
        try {
          if (listening) {
            listening = false;
            recognition && recognition.stop();
            voiceBtn.textContent = 'Start Voice Input';
            return;
          }
          finalTranscript = answerBox.value ? answerBox.value + ' ' : '';
          recognition = buildRecognition();
          recognition.start();
          listening = true;
          const label = voiceLanguage ? voiceLanguage.options[voiceLanguage.selectedIndex].text : 'Bangla voice';
          voiceBtn.textContent = 'Stop Voice Input';
          await logEvent('speech_started', `Student started voice input: ${label}`);
        } catch (e) {
          listening = false;
          voiceBtn.textContent = 'Start Voice Input';
          await logEvent('speech_error', e.message || 'Speech recognition error');
        }
      });
    }
  }
})();
