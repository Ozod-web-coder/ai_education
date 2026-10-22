import { getInitData } from "./telegram";

const BASE = (import.meta.env.VITE_API_URL || "/api").replace(/\/$/, "");
const CENTER = import.meta.env.VITE_CENTER_SLUG || "demo";
const DEV_TOKEN = import.meta.env.DEV ? import.meta.env.VITE_DEV_TOKEN : "";

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
    const response = await fetch(`${BASE}/auth/telegram/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ center: CENTER, init_data: initData }),
    });
    const data = await parse(response);
    if (!response.ok) {
      throw new ApiError(response.status, errorText(data, "Не удалось войти через Telegram."), "auth");
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
    throw new ApiError(0, "Нет связи с сервером. Проверьте интернет.", "network");
  }

  if (response.status === 401 && retry && !DEV_TOKEN) {
    accessToken = null; // токен истёк: входим заново по initData и повторяем запрос
    return request(path, { method, body, params }, false);
  }

  const data = await parse(response);
  if (!response.ok) {
    const code = response.status === 403 ? "forbidden" : "http";
    throw new ApiError(response.status, errorText(data, "Что-то пошло не так."), code);
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
