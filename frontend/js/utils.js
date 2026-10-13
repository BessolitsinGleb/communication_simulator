/*
  utils.js
  Небольшие переиспользуемые хелперы интерфейса, общие для всех страниц.
*/

const Utils = {
  uuid() {
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  },

  // Плавное появление блоков снизу вверх при прокрутке (без насильного smooth-scroll)
  initFadeInOnScroll(selector = '.fade-in-on-scroll') {
    const items = document.querySelectorAll(selector);
    if (!items.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );
    items.forEach((el) => observer.observe(el));
  },

  toast(message, type = 'error') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const el = document.createElement('div');
    el.className = `toast toast--${type}`;
    el.textContent = message;
    container.appendChild(el);
    requestAnimationFrame(() => el.classList.add('is-visible'));
    setTimeout(() => {
      el.classList.remove('is-visible');
      setTimeout(() => el.remove(), 250);
    }, 4200);
  },

  setLoading(button, isLoading) {
    if (!button) return;
    button.disabled = isLoading;
    button.classList.toggle('is-loading', isLoading);
  },

  // Возвращает на страницу входа, если токена нет
  requireAuth() {
    if (!Api.TokenStorage.isAuthenticated()) {
      window.location.href = 'auth.html';
      return false;
    }
    return true;
  },

  formatErr(error) {
    if (error instanceof Api.ApiError) return error.message;
    return 'Что-то пошло не так. Попробуйте ещё раз.';
  },
};
