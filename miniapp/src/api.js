import { getInitData } from "./telegram";

const BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const CENTER = import.meta.env.VITE_CENTER_SLUG || "demo";
const DEV_TOKEN = import.meta.env.DEV ? import.meta.env.VITE_DEV_TOKEN : "";

// Откуда реально берутся данные: на Vercel без VITE_API_URL это адрес самого Mini App, а не backend.
const API_ORIGIN = (() => {
  try {
    return new URL(BASE, window.location.origin).origin;
  } catch {
    return BASE;
  }
})();

export class ApiError extends Error {
  constructor(status, message, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

let accessToken = null;

function errorText(data, fallback) {
  if (!data) return fallback;
  if (typeof data.detail === "string") return data.detail;
  const first = Object.values(data)[0];
  if (Array.isArray(first) && typeof first[0] === "string") return first[0];
  return fallback;
}

function networkError() {
  return new ApiError(
    0,
    `Нет связи с ${API_ORIGIN}. Проверьте VITE_API_URL и что backend доступен; если адрес верный, добавьте ${window.location.origin} в CORS_ALLOWED_ORIGINS на backend.`,
    "network",
  );
}

/** Текст ошибки с HTTP-кодом. Не-JSON ответ значит, что по этому адресу отвечает не наш API. */
function failText(response, data, fallback) {
  if (data === null) {
    return `${API_ORIGIN} ответил не как API (HTTP ${response.status}). Проверьте VITE_API_URL: он должен вести на backend и заканчиваться на /api.`;
  }
  return `${errorText(data, fallback)} (HTTP ${response.status})`;
}

async function parse(response) {
  if (response.status === 204) return null;
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function login() {
  const initData = getInitData();
  if (initData) {
    let response;
    try {
      response = await fetch(`${BASE}/auth/telegram/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ center: CENTER, init_data: initData }),
      });
    } catch {
      throw networkError();
    }
    const data = await parse(response);
    if (!response.ok) {
      const hint = data === null ? "" : ` Центр: «${CENTER}» (VITE_CENTER_SLUG). Откройте Mini App из того же бота, чей токен записан в центре.`;
      throw new ApiError(response.status, failText(response, data, "Не удалось войти через Telegram.") + hint, "auth");
    }
    accessToken = data.access;
    return;
  }
  if (DEV_TOKEN) {
    accessToken = DEV_TOKEN;
    return;
  }
  throw new ApiError(0, "Откройте приложение из Telegram.", "no-telegram");
}

async function request(path, { method = "GET", body, params } = {}, retry = true) {
  if (!accessToken) await login();

  const query = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") query.set(key, value);
  });
  const qs = query.toString();
  const url = `${BASE}/c/${CENTER}${path}${qs ? `?${qs}` : ""}`;

  let response;
  try {
    response = await fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(body ? { "Content-Type": "application/json" } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw networkError();
  }

  if (response.status === 401 && retry && !DEV_TOKEN) {
    accessToken = null; // токен истёк: входим заново по initData и повторяем запрос
    return request(path, { method, body, params }, false);
  }

  const data = await parse(response);
  if (!response.ok) {
    const code = response.status === 403 ? "forbidden" : "http";
    throw new ApiError(response.status, code === "forbidden" ? errorText(data, "Нет доступа.") : failText(response, data, "Что-то пошло не так."), code);
  }
  return data;
}

export const listLeads = (params) => request("/admin/leads/", { params });
export const getStats = () => request("/admin/leads/stats/");
export const getLead = (id) => request(`/admin/leads/${id}/`);
export const updateLead = (id, patch) => request(`/admin/leads/${id}/`, { method: "PATCH", body: patch });
export const confirmLead = (id) => request(`/admin/leads/${id}/confirm/`, { method: "POST" });
export const deleteLead = (id) => request(`/admin/leads/${id}/`, { method: "DELETE" });
export const listCourses = () => request("/courses/");
