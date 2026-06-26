import { apiFetch } from "./client";

export interface Role {
  id: string;
  name: string;
  is_admin_role: boolean;
}

export interface Permissions {
  can_chat: boolean;
  can_view_docs: boolean;
  can_view_reports: boolean;
  can_view_dashboards: boolean;
  can_view_tethers: boolean;
}

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
  role: Role | null;
  permissions: Permissions;
}

export function fetchCsrf(): Promise<{ detail: string }> {
  return apiFetch("/api/v1/auth/csrf/");
}

export function fetchMe(): Promise<CurrentUser> {
  return apiFetch("/api/v1/auth/me/");
}

export function login(username: string, password: string): Promise<CurrentUser> {
  return apiFetch("/api/v1/auth/login/", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
}

export function logout(): Promise<void> {
  return apiFetch("/api/v1/auth/logout/", { method: "POST" });
}
