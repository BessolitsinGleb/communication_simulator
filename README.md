# Тренажёр общения с клиентом — фронтенд

Статический фронтенд (HTML/CSS/vanilla JS, без сборщика) под уже существующий backend.
Архитектура специально разбита на мелкие файлы — платформа будет расти,
и каждая новая страница/эндпоинт добавляется без переписывания существующих.

## Структура

```
frontend/
├── index.html              # редирект на home.html / auth.html по наличию токена
├── pages/
│   ├── auth.html            # вход, регистрация, подтверждение почты
│   ├── home.html             # профиль + переход к диалогам
│   ├── audio-dialog.html    # голосовой звонок
│   └── text-dialog.html     # текстовый диалог
├── css/
│   ├── variables.css        # дизайн-токены: цвета, радиусы, тени, типографика
│   ├── base.css              # сброс, типографика, skeleton, fade-in-on-scroll
│   ├── components.css        # кнопки, поля, карточки, nav, toast — общие для всех страниц
│   ├── auth.css / home.css / audio-dialog.css / text-dialog.css
└── js/
    ├── config.js              # ЕДИНСТВЕННОЕ место с адресом backend (API_BASE_URL)
    ├── api.js                 # весь fetch-слой: токен, заголовки, методы под каждый эндпоинт
    ├── utils.js                # uuid, toast, скролл-анимации, guard авторизации
    ├── auth.js / home.js / audio-dialog.js / text-dialog.js
```

## Подключение к backend

Один файл — `js/config.js`:

```js
window.APP_CONFIG = {
  API_BASE_URL: 'http://localhost:8000',
};
```

Меняете `API_BASE_URL` на адрес реального сервера — остальной код трогать не нужно.

## Как добавлять новую страницу

1. `pages/new-page.html` — подключить `variables.css`, `base.css`, `components.css`,
   свой `css/new-page.css`, затем `config.js`, `api.js`, `utils.js`, свой `js/new-page.js`.
2. Новые вызовы backend добавляются как методы объекта `Api` в `js/api.js` —
   остальной код никогда не делает `fetch()` напрямую.
3. Все страницы (кроме `auth.html`) должны начинаться с `if (!Utils.requireAuth()) return;`.

## Реализованный функционал (по ТЗ)

- **Авторизация**: `/reg/regis`, `/reg/login`, `/reg/verify_email`, `/reg/resend_code`.
  После подтверждения почты выполняется автологин (`/reg/login` с теми же данными).
- **Главная**: `/reg/me` подгружается автоматически, карточка со skeleton-заглушкой на время загрузки.
- **Аудиозвонок**: `/dialog/choose_voice`, затем цикл `/dialog/process_turn/{session_id}`
  (запись реплики через MediaRecorder → mp3-ответ проигрывается → следующая реплика),
  завершение — `/dialog/close_session/{session_id}`.
- **Текстовый диалог**: `/text/send/{session_id}` в цикле до `end_dialog`,
  досрочное завершение — `/text/close_session/{session_id}`.

`session_id` для обеих диалоговых сессий генерируется на клиенте (`crypto.randomUUID`),
так как выделенного эндпоинта «создать сессию» в ТЗ нет — сессия открывается самим
первым вызовом `process_turn` / `send`.

## Заметки по реализации

- Все токен/пользовательские данные хранятся в `localStorage` (ключ `trainer_access_token`).
- Цветовая палитра, скругления, стекломорфизм навигации, золотое свечение кнопок,
  skeleton-загрузка и fade-in-on-scroll реализованы в `variables.css` / `base.css` / `components.css`
  строго по ТЗ.
- Код ориентирован на реальные значения бэкенда: `level` — `easy/normal/hard`,
  `mode` — `easy/norm/hard` (обратите внимание, у `mode` средний вариант — `norm`, не `normal`).
