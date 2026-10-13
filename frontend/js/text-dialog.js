/*
  text-dialog.js — логика страницы текстового диалога (pages/text-dialog.html)

  Цикл диалога:
    /text/send/{session_id} — вызывается на каждое сообщение пользователя;
    пока status "success" и end_dialog/end_call не true, диалог продолжается.
    /text/close_session/{session_id} — досрочное завершение по кнопке сверху.
*/

(function () {
  if (!Utils.requireAuth()) return;

  const setupScreen = document.getElementById('setup-screen');
  const chatScreen = document.getElementById('chat-screen');
  const endScreen = document.getElementById('end-screen');

  const startChatBtn = document.getElementById('start-chat-btn');
  const setupError = document.getElementById('setup-error');

  const messagesEl = document.getElementById('messages');
  const composer = document.getElementById('composer');
  const messageInput = document.getElementById('message-input');
  const sendBtn = document.getElementById('send-btn');
  const closeChatBtn = document.getElementById('close-chat-btn');

  const endTitle = document.getElementById('end-title');
  const endMessage = document.getElementById('end-message');
  const restartBtn = document.getElementById('end-restart-btn');

  const state = {
    level: 'easy',
    mode: 'easy',
    sessionId: null,
    isSending: false,
    isEnded: false,
  };

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

  wireSegmented('level-picker', (v) => (state.level = v));
  wireSegmented('mode-picker', (v) => (state.mode = v));

  startChatBtn.addEventListener('click', () => {
    setupError.textContent = '';
    state.sessionId = Utils.uuid();
    state.isEnded = false;
    messagesEl.innerHTML = '';
    addBubble('system', 'Диалог начат. Напишите первое сообщение.');

    setupScreen.hidden = true;
    endScreen.hidden = true;
    chatScreen.hidden = false;
    messageInput.focus();
  });

  function addBubble(kind, text) {
    const bubble = document.createElement('div');
    bubble.className = `bubble bubble--${kind}`;
    bubble.textContent = text;
    messagesEl.appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  function addTypingBubble() {
    const bubble = document.createElement('div');
    bubble.className = 'bubble bubble--bot bubble--typing skeleton';
    bubble.id = 'typing-bubble';
    messagesEl.appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  function removeTypingBubble() {
    const el = document.getElementById('typing-bubble');
    if (el) el.remove();
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  composer.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (state.isSending || state.isEnded) return;

    const text = messageInput.value.trim();
    if (!text) return;

    addBubble('user', text);
    messageInput.value = '';
    state.isSending = true;
    Utils.setLoading(sendBtn, true);
    addTypingBubble();

    try {
      const data = await Api.sendTextTurn(state.sessionId, {
        message: text,
        level: state.level,
        mode: state.mode,
      });

      removeTypingBubble();
      const replyText = data.response ?? data.text_to_speak ?? '';
      if (replyText) addBubble('bot', replyText);

      const isEnded = data.end_dialog === true || data.end_call === true;
      if (isEnded) {
        state.isEnded = true;
        setTimeout(() => {
          finishChat({
            title: data.status === 'timeout' ? 'Время вышло' : 'Диалог завершён',
            message: replyText || 'Сессия завершена сервером, история сохранена.',
          });
        }, 700);
      }
    } catch (error) {
      removeTypingBubble();
      Utils.toast(Utils.formatErr(error), 'error');
    } finally {
      state.isSending = false;
      Utils.setLoading(sendBtn, false);
      messageInput.focus();
    }
  });

  closeChatBtn.addEventListener('click', async () => {
    if (state.isEnded) return;
    Utils.setLoading(closeChatBtn, true);
    try {
      await Api.closeTextSession(state.sessionId);
    } catch (error) {
      // сессия могла быть уже закрыта — не блокируем выход
    } finally {
      Utils.setLoading(closeChatBtn, false);
    }
    state.isEnded = true;
    finishChat({
      title: 'Диалог завершён',
      message: 'Вы завершили диалог досрочно.',
    });
  });

  function finishChat({ title, message }) {
    chatScreen.hidden = true;
    endTitle.textContent = title;
    endMessage.textContent = message;
    endScreen.hidden = false;
  }

  restartBtn.addEventListener('click', () => {
    endScreen.hidden = true;
    setupScreen.hidden = false;
  });

  Utils.initFadeInOnScroll();
})();
