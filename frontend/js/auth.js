/*
  auth.js — логика страницы входа/регистрации (pages/auth.html)

  Поток регистрации:
    1) POST /reg/regis            -> код отправлен на почту
    2) показываем форму подтверждения
    3) POST /reg/verify_email     -> почта подтверждена
    4) автологин: POST /reg/login с теми же email/password, сохранённый токен
    5) редирект на home.html
*/

(function () {
  if (Api.TokenStorage.isAuthenticated()) {
    window.location.href = 'home.html';
    return;
  }

  const tabLogin = document.getElementById('tab-login');
  const tabRegister = document.getElementById('tab-register');
  const formLogin = document.getElementById('form-login');
  const formRegister = document.getElementById('form-register');
  const formVerify = document.getElementById('form-verify');

  // Пароль временно хранится в памяти между шагом регистрации и автологином.
  // Никуда, кроме запроса /reg/login, не отправляется и не сохраняется.
  let pendingCredentials = null;

  function showForm(form) {
    [formLogin, formRegister, formVerify].forEach((f) => {
      f.hidden = f !== form;
    });
  }

  function setTab(target) {
    const isLogin = target === 'login';
    tabLogin.setAttribute('aria-pressed', String(isLogin));
    tabRegister.setAttribute('aria-pressed', String(!isLogin));
    showForm(isLogin ? formLogin : formRegister);
  }

  tabLogin.addEventListener('click', () => setTab('login'));
  tabRegister.addEventListener('click', () => setTab('register'));

  function setError(id, message) {
    document.getElementById(id).textContent = message || '';
  }

  async function afterAuthSuccess(accessToken) {
    Api.TokenStorage.set(accessToken);
    window.location.href = 'home.html';
  }

  /* ---------- Вход ---------- */
  formLogin.addEventListener('submit', async (event) => {
    event.preventDefault();
    setError('login-error', '');
    const submitBtn = document.getElementById('login-submit');
    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;

    Utils.setLoading(submitBtn, true);
    try {
      const { access_token } = await Api.login({ email, password });
      await afterAuthSuccess(access_token);
    } catch (error) {
      setError('login-error', Utils.formatErr(error));
    } finally {
      Utils.setLoading(submitBtn, false);
    }
  });

  /* ---------- Регистрация ---------- */
  formRegister.addEventListener('submit', async (event) => {
    event.preventDefault();
    setError('register-error', '');
    const submitBtn = document.getElementById('register-submit');
    const username = document.getElementById('reg-username').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;

    Utils.setLoading(submitBtn, true);
    try {
      await Api.register({ username, email, password });
      pendingCredentials = { email, password };
      document.getElementById('verify-email-display').textContent = email;
      showForm(formVerify);
      Utils.toast('Код отправлен на почту', 'success');
    } catch (error) {
      setError('register-error', Utils.formatErr(error));
    } finally {
      Utils.setLoading(submitBtn, false);
    }
  });

  /* ---------- Подтверждение почты + автологин ---------- */
  formVerify.addEventListener('submit', async (event) => {
    event.preventDefault();
    setError('verify-error', '');
    const submitBtn = document.getElementById('verify-submit');
    const code = document.getElementById('verify-code').value.trim();

    if (!pendingCredentials) {
      setError('verify-error', 'Сессия регистрации потеряна, начните заново.');
      return;
    }

    Utils.setLoading(submitBtn, true);
    try {
      await Api.verifyEmail({ email: pendingCredentials.email, code });
      const { access_token } = await Api.login(pendingCredentials);
      await afterAuthSuccess(access_token);
    } catch (error) {
      setError('verify-error', Utils.formatErr(error));
    } finally {
      Utils.setLoading(submitBtn, false);
    }
  });

  document.getElementById('resend-code').addEventListener('click', async () => {
    if (!pendingCredentials) return;
    const btn = document.getElementById('resend-code');
    Utils.setLoading(btn, true);
    try {
      await Api.resendCode({ email: pendingCredentials.email });
      Utils.toast('Код отправлен повторно', 'success');
    } catch (error) {
      Utils.toast(Utils.formatErr(error), 'error');
    } finally {
      Utils.setLoading(btn, false);
    }
  });

  Utils.initFadeInOnScroll();
})();
