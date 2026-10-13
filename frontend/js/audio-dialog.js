/*
  audio-dialog.js — логика страницы голосового звонка (pages/audio-dialog.html)

  Цикл диалога:
    1) /dialog/choose_voice          — один раз перед звонком
    2) /dialog/process_turn/{id}     — цикл: отправляем запись реплики
       пользователя, получаем ЛИБО mp3 (реплика собеседника, диалог
       продолжается), ЛИБО JSON с end_call: true (диалог завершён)
    3) /dialog/close_session/{id}    — досрочное завершение звонка пользователем
*/

(function () {
  if (!Utils.requireAuth()) return;

  const setupScreen = document.getElementById('setup-screen');
  const callScreen = document.getElementById('call-screen');
  const endScreen = document.getElementById('end-screen');

  const startCallBtn = document.getElementById('start-call-btn');
  const setupError = document.getElementById('setup-error');

  const callAvatar = document.getElementById('call-avatar');
  const callStatus = document.getElementById('call-status');
  const callTimerEl = document.getElementById('call-timer');
  const botLine = document.getElementById('bot-line');
  const micBtn = document.getElementById('mic-btn');
  const hangupBtn = document.getElementById('hangup-btn');
  const callHint = document.getElementById('call-hint');
  const botAudio = document.getElementById('bot-audio');

  const endTitle = document.getElementById('end-title');
  const endMessage = document.getElementById('end-message');
  const restartBtn = document.getElementById('end-restart-btn');

  const state = {
    voice: 'woman',
    level: 'easy',
    mode: 'easy',
    sessionId: null,
    mediaStream: null,
    recorder: null,
    chunks: [],
    isRecording: false,
    isBusy: false, // ждём ответ сервера или проигрывается аудио
    timerHandle: null,
    startedAt: null,
  };

  /* ---------- Пикеры настроек ---------- */

  function wireSegmented(containerId, onSelect) {
    const container = document.getElementById(containerId);
    container.addEventListener('click', (event) => {
      const btn = event.target.closest('.segmented__option');
      if (!btn) return;
      [...container.children].forEach((c) => c.setAttribute('aria-pressed', 'false'));
      btn.setAttribute('aria-pressed', 'true');
      onSelect(btn.dataset.value);
    });
  }

  wireSegmented('voice-picker', (v) => (state.voice = v));
  wireSegmented('level-picker', (v) => (state.level = v));
  wireSegmented('mode-picker', (v) => (state.mode = v));

  /* ---------- Запуск звонка ---------- */

  startCallBtn.addEventListener('click', async () => {
    setupError.textContent = '';
    Utils.setLoading(startCallBtn, true);
    try {
      await Api.chooseVoice(state.voice);
      state.mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (error) {
      if (error instanceof Api.ApiError) {
        setupError.textContent = Utils.formatErr(error);
      } else {
        setupError.textContent = 'Не удалось получить доступ к микрофону. Разрешите доступ и попробуйте снова.';
      }
      Utils.setLoading(startCallBtn, false);
      return;
    }
    Utils.setLoading(startCallBtn, false);
    beginCallScreen();
  });

  function beginCallScreen() {
    state.sessionId = Utils.uuid();
    setupScreen.hidden = true;
    endScreen.hidden = true;
    callScreen.hidden = false;

    micBtn.disabled = false;
    micBtn.setAttribute('aria-pressed', 'false');
    botLine.textContent = '';
    setStatus('idle', 'Ваш ход');
    callHint.textContent = 'Нажмите на микрофон и начните говорить';

    state.startedAt = Date.now();
    callTimerEl.textContent = '00:00';
    state.timerHandle = setInterval(updateTimer, 1000);
  }

  function updateTimer() {
    const elapsed = Math.floor((Date.now() - state.startedAt) / 1000);
    const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
    const ss = String(elapsed % 60).padStart(2, '0');
    callTimerEl.textContent = `${mm}:${ss}`;
  }

  function setStatus(kind, text) {
    callStatus.textContent = text;
    callAvatar.classList.toggle('is-active', kind === 'recording' || kind === 'busy' || kind === 'playing');
  }

  /* ---------- Запись хода пользователя ---------- */

  micBtn.addEventListener('click', () => {
    if (state.isBusy) return;
    if (!state.isRecording) {
      startRecording();
    } else {
      stopRecordingAndSend();
    }
  });

  function pickMimeType() {
    const candidates = ['audio/webm', 'audio/webm;codecs=opus', 'audio/mp4', 'audio/ogg'];
    return candidates.find((type) => window.MediaRecorder && MediaRecorder.isTypeSupported(type)) || '';
  }

  function startRecording() {
    state.chunks = [];
    const mimeType = pickMimeType();
    state.recorder = mimeType
      ? new MediaRecorder(state.mediaStream, { mimeType })
      : new MediaRecorder(state.mediaStream);

    state.recorder.addEventListener('dataavailable', (e) => {
      if (e.data && e.data.size > 0) state.chunks.push(e.data);
    });

    state.recorder.start();
    state.isRecording = true;
    micBtn.setAttribute('aria-pressed', 'true');
    setStatus('recording', 'Вы говорите…');
    callHint.textContent = 'Нажмите на микрофон ещё раз, чтобы отправить реплику';
  }

  function stopRecordingAndSend() {
    if (!state.recorder) return;
    state.isRecording = false;
    micBtn.setAttribute('aria-pressed', 'false');
    micBtn.disabled = true;

    state.recorder.addEventListener(
      'stop',
      async () => {
        const blob = new Blob(state.chunks, { type: state.recorder.mimeType || 'audio/webm' });
        await sendTurn(blob);
      },
      { once: true }
    );
    state.recorder.stop();
  }

  async function sendTurn(blob) {
    state.isBusy = true;
    setStatus('busy', 'Ожидание ответа…');
    callHint.textContent = 'Собеседник обдумывает ответ';

    try {
      const result = await Api.processAudioTurn(state.sessionId, {
        level: state.level,
        mode: state.mode,
        file: blob,
      });

      if (result.type === 'audio') {
        await playBotAudio(result.blob);
        state.isBusy = false;
        micBtn.disabled = false;
        setStatus('idle', 'Ваш ход');
        callHint.textContent = 'Нажмите на микрофон и начните говорить';
        return;
      }

      // type === 'json' — сервер всегда завершает диалог этим ответом
      const data = result.data;
      botLine.textContent = data.text_to_speak || '';
      endCall({
        title: data.status === 'timeout' ? 'Время вышло' : 'Звонок завершён',
        message: data.text_to_speak || 'Сессия завершена сервером.',
        closeOnServer: false, // сервер уже завершил сессию сам
      });
    } catch (error) {
      Utils.toast(Utils.formatErr(error), 'error');
      state.isBusy = false;
      micBtn.disabled = false;
      setStatus('idle', 'Ваш ход');
      callHint.textContent = 'Попробуйте ещё раз';
    }
  }

  function playBotAudio(blob) {
    return new Promise((resolve) => {
      const url = URL.createObjectURL(blob);
      botAudio.src = url;
      setStatus('playing', 'Собеседник говорит…');
      callHint.textContent = '';

      const finish = () => {
        URL.revokeObjectURL(url);
        botAudio.removeEventListener('ended', finish);
        botAudio.removeEventListener('error', finish);
        resolve();
      };
      botAudio.addEventListener('ended', finish);
      botAudio.addEventListener('error', finish);

      botAudio.play().catch(() => {
        Utils.toast('Не удалось воспроизвести ответ собеседника', 'error');
        finish();
      });
    });
  }

  /* ---------- Завершение звонка ---------- */

  hangupBtn.addEventListener('click', async () => {
    hangupBtn.disabled = true;
    if (state.isRecording && state.recorder) {
      state.recorder.stop();
    }
    await endCall({
      title: 'Звонок завершён',
      message: 'Вы завершили звонок.',
      closeOnServer: true,
    });
  });

  async function endCall({ title, message, closeOnServer }) {
    clearInterval(state.timerHandle);

    if (closeOnServer && state.sessionId) {
      try {
        await Api.closeAudioSession(state.sessionId);
      } catch (error) {
        // сессия уже могла быть закрыта — не блокируем интерфейс
      }
    }

    if (state.mediaStream) {
      state.mediaStream.getTracks().forEach((track) => track.stop());
      state.mediaStream = null;
    }

    callScreen.hidden = true;
    endTitle.textContent = title;
    endMessage.textContent = message;
    endScreen.hidden = false;
    hangupBtn.disabled = false;
  }

  restartBtn.addEventListener('click', () => {
    endScreen.hidden = true;
    setupScreen.hidden = false;
  });

  Utils.initFadeInOnScroll();
})();
