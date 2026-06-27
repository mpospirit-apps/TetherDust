import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getAgentStatus } from "../api/chat";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../hooks/useTheme";

function linkClass({ isActive }: { isActive: boolean }): string {
  return isActive ? "navbar-link active" : "navbar-link";
}

// Top navigation, ported from the legacy base template: brand + permission-gated
// section links + a user dropdown (theme toggle, logout).
export function Navbar() {
  const { user, logout } = useAuth();
  const { theme, toggle } = useTheme();
  const [menuOpen, setMenuOpen] = useState(false);
  const agentQuery = useQuery({
    queryKey: ["chat", "agent-status"],
    queryFn: getAgentStatus,
    refetchInterval: 20000,
    enabled: !!user,
  });

  useEffect(() => {
    function close() {
      setMenuOpen(false);
    }
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, []);

  if (!user) {
    return null;
  }
  const perms = user.permissions;

  return (
    <nav className="navbar">
      <NavLink to="/" className="navbar-brand">
        <img src="/images/tetherdust.png" alt="TetherDust" className="brand-icon" />
        Tether<span>Dust</span>
      </NavLink>
      <div className="navbar-menu">
        {perms.can_chat && (
          <NavLink to="/chat" className={linkClass}>
            Chat
          </NavLink>
        )}
        {perms.can_view_docs && (
          <NavLink to="/docs" className={linkClass}>
            Docs
          </NavLink>
        )}
        {perms.can_view_reports && (
          <NavLink to="/reports" className={linkClass}>
            Reports
          </NavLink>
        )}
        {perms.can_view_dashboards && (
          <NavLink to="/dashboards" className={linkClass}>
            Dashboards
          </NavLink>
        )}
        {perms.can_view_tethers && (
          <NavLink to="/tethers" className={linkClass}>
            Tethers
          </NavLink>
        )}
        {user.is_staff && (
          <NavLink to="/admin" className={linkClass}>
            Control
          </NavLink>
        )}
        <div className="user-dropdown">
          <button
            className="user-dropdown__trigger"
            aria-label="User menu"
            onClick={(event) => {
              event.stopPropagation();
              setMenuOpen((open) => !open);
            }}
          >
            <i className="fa-solid fa-circle-user" />
          </button>
          <div
            className={menuOpen ? "user-dropdown__menu is-open" : "user-dropdown__menu"}
            onClick={(event) => event.stopPropagation()}
          >
            <span className="user-dropdown__username">{user.username}</span>
            <div className="user-dropdown__divider" />
            <div className="user-dropdown__agent">
              <span
                className={
                  agentQuery.data?.connected
                    ? "agent-status-dot is-connected"
                    : "agent-status-dot is-disconnected"
                }
              />
              <span className="user-dropdown__agent-name">
                {agentQuery.data?.name ?? "No agent active"}
              </span>
            </div>
            <div className="user-dropdown__divider" />
            <button className="user-dropdown__item" onClick={toggle} aria-label="Toggle dark mode">
              <i className={theme === "dark" ? "fa-solid fa-sun" : "fa-solid fa-moon"} />
              <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
            </button>
            <button className="user-dropdown__item" onClick={() => void logout()}>
              <i className="fa-solid fa-right-from-bracket" />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}
