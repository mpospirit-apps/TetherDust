// Thin fetch wrapper for the single-origin API. Sends cookies (session auth) and
// echoes the CSRF token on unsafe methods, matching Django's expectations.

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp("(^|;\\s*)" + name + "=([^;]*)"));
  return match ? decodeURIComponent(match[2]) : null;
}

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export class ApiError extends Error {
  readonly status: number;
  readonly data: unknown;

  constructor(status: number, data: unknown) {
    super(`API error ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);

  if (UNSAFE_METHODS.has(method)) {
    const token = getCookie("csrftoken");
    if (token) headers.set("X-CSRFToken", token);
  }
  if (options.body != null && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(path, { ...options, headers, credentials: "include" });
  const contentType = response.headers.get("Content-Type") ?? "";
  const data: unknown = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    throw new ApiError(response.status, data);
  }
  return data as T;
}

// Pull a human message out of a DRF error body: {detail}, {error}, or the
// field-validation shape { field: ["msg", ...] | "msg" }.
export function apiErrorDetail(err: unknown, fallback = "Request failed."): string {
  if (err instanceof ApiError && err.data && typeof err.data === "object") {
    const d = err.data as Record<string, unknown>;
    if (typeof d.detail === "string") return d.detail;
    if (typeof d.error === "string") return d.error;
    const parts: string[] = [];
    for (const [key, val] of Object.entries(d)) {
      const msg = Array.isArray(val) ? val.map(String).join(" ") : String(val);
      parts.push(key === "non_field_errors" ? msg : `${key}: ${msg}`);
    }
    if (parts.length > 0) return parts.join(" • ");
  }
  return fallback;
}
