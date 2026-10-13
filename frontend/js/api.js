/*
  api.js
  Единая точка общения с backend. Все страницы ходят на сервер только
  через объект Api — это даёт масштабируемость: новый эндпоинт = новый
  метод здесь, а не разбросанные fetch() по всем файлам.
*/

const TOKEN_KEY = "trainer_access_token";

class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

const TokenStorage = {
  get() {
    return localStorage.getItem(TOKEN_KEY);
  },
  set(token) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
  isAuthenticated() {
    return Boolean(TokenStorage.get());
  },
};

function buildUrl(path) {
  const base = window.APP_CONFIG.API_BASE_URL.replace(/\/$/, "");
  return `${base}${path}`;
}

function authHeader() {
  const token = TokenStorage.get();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function extractErrorMessage(response) {
  try {
    const data = await response.clone().json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail) && data.detail[0]?.msg)
      return data.detail[0].msg;
    if (data.message) return data.message;
  } catch (_) {
    /* тело не JSON — используем статус ниже */
  }
  return `Ошибка запроса (код ${response.status})`;
}

async function request(
  path,
  { method = "GET", json, formData, headers = {} } = {},
) {
  const finalHeaders = { ...authHeader(), ...headers };
  let body;

  if (json !== undefined) {
    finalHeaders["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (formData !== undefined) {
    body = formData; // Content-Type (с boundary) браузер выставит сам
  }

  let response;
  try {
    response = await fetch(buildUrl(path), {
      method,
      headers: finalHeaders,
      body,
    });
  } catch (networkError) {
    throw new ApiError(
      "Не удалось связаться с сервером. Проверьте соединение.",
      0,
    );
  }

  if (!response.ok) {
    throw new ApiError(await extractErrorMessage(response), response.status);
  }
  return response;
}

const Api = {
  TokenStorage,
  ApiError,

  /* ---------- /reg — регистрация и авторизация ---------- */

  async register({ username, email, password }) {
    const response = await request("/reg/regis", {
      method: "POST",
      json: { username, email, password },
    });
    return response.json(); // { message }
  },

  async login({ email, password }) {
    const response = await request("/reg/login", {
      method: "POST",
      json: { email, password },
    });
    return response.json(); // { access_token, token_type }
  },

  async verifyEmail({ email, code }) {
    const response = await request("/reg/verify_email", {
      method: "POST",
      json: { email, code },
    });
    return response.json(); // { message }
  },

  async resendCode({ email }) {
    const response = await request("/reg/resend_code", {
      method: "POST",
      json: { email },
    });
    return response.json(); // { message }
  },

  async me() {
    const response = await request("/reg/me", { method: "GET" });
    return response.json(); // { user_id, username, email }
  },

  /* ---------- /dialog — аудио-диалог ---------- */

  async chooseVoice(voice) {
    const response = await request("/dialog/choose_voice", {
      method: "POST",
      json: { voice },
    });
    return response.json(); // { status, choosen_voice }
  },

  // Ответ бывает ЛИБО mp3-файлом, ЛИБО JSON (таймаут / финальная реплика).
  // Тип различаем по заголовку Content-Type.
  async processAudioTurn(sessionId, { level, mode, file }) {
    const formData = new FormData();
    formData.append("level", level);
    formData.append("mode", mode);
    formData.append("file", file, "turn.webm");

    const response = await request(`/dialog/process_turn/${sessionId}`, {
      method: "POST",
      formData,
    });

    const contentType = response.headers.get("Content-Type") || "";
    if (contentType.includes("audio")) {
      return { type: "audio", blob: await response.blob() };
    }
    return { type: "json", data: await response.json() };
  },

  async closeAudioSession(sessionId) {
    const response = await request(`/dialog/close_session/${sessionId}`, {
      method: "DELETE",
    });
    return response.json();
  },

  /* ---------- /text — текстовый диалог ---------- */

  async sendTextTurn(sessionId, { message, level, mode }) {
    const response = await request(`/text/send/${sessionId}`, {
      method: "POST",
      json: { message, level, mode },
    });
    return response.json();
  },

  async closeTextSession(sessionId) {
    const response = await request(`/text/close_session/${sessionId}`, {
      method: "DELETE",
    });
    return response.json();
  },
};
