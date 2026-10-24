// Talks to the Reachwise server. Its address comes from public/config.js (editable after
// deployment), or VITE_API_URL at build time; empty means "the same address as the website".
export const API_URL = ((typeof window !== "undefined" && window.PROFMAIL_API_URL) || import.meta.env.VITE_API_URL || "")
  .replace(/\/+$/, "");
const TOKEN_KEY = "profmail_token";

export function getToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}
export function setToken(t) {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ }
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(path, { method = "GET", body, form } = {}) {
  // Tells ngrok's free plan not to answer with its browser warning page (harmless elsewhere)
  const headers = { "ngrok-skip-browser-warning": "1" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res;
  try {
    res = await fetch(API_URL + path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Can't reach the Reachwise server. Check your internet connection, or try again in a minute.");
  }
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("profmail:signed-out"));
  }
  const type = res.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    let msg = typeof data === "object" ? data.detail : data;
    if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join("; ");
    throw new ApiError(res.status, msg || `Something went wrong (${res.status})`);
  }
  return data;
}

export async function download(path, filename) {
  const res = await fetch(API_URL + path, {
    headers: { Authorization: `Bearer ${getToken()}`, "ngrok-skip-browser-warning": "1" },
  });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function when(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function day(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}
