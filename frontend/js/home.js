/*
  home.js — логика главной страницы (pages/home.html)
*/

(function () {
  if (!Utils.requireAuth()) return;

  async function loadProfile() {
    try {
      const user = await Api.me();

      document.getElementById('profile-name-skeleton').hidden = true;
      document.getElementById('profile-email-skeleton').hidden = true;
      document.getElementById('profile-avatar').classList.remove('skeleton');

      const initials = user.username.slice(0, 2).toUpperCase();
      document.getElementById('profile-avatar').textContent = initials;
      document.getElementById('profile-username').textContent = user.username;
      document.getElementById('profile-email').textContent = user.email;
      document.getElementById('profile-id').textContent = `ID пользователя: ${user.user_id}`;
      document.getElementById('profile-details').hidden = false;
    } catch (error) {
      Utils.toast(Utils.formatErr(error), 'error');
      if (error instanceof Api.ApiError && (error.status === 401 || error.status === 403)) {
        Api.TokenStorage.clear();
        window.location.href = 'auth.html';
      }
    }
  }

  document.getElementById('logout-btn').addEventListener('click', () => {
    Api.TokenStorage.clear();
    window.location.href = 'auth.html';
  });

  loadProfile();
  Utils.initFadeInOnScroll();
})();
