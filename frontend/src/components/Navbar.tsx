import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { getAgentStatus } from "../api/chat";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../hooks/useTheme";

const NAV_LINKS = [
	{
		to: "/chat",
		label: "Chat",
		icon: "fa-solid fa-comments",
		color: "var(--c-cyan)",
		perm: "can_chat",
	},
	{
		to: "/docs",
		label: "Docs",
		icon: "fa-solid fa-file-lines",
		color: "var(--c-lime)",
		perm: "can_view_docs",
	},
	{
		to: "/reports",
		label: "Reports",
		icon: "fa-solid fa-table-list",
		color: "var(--c-orange)",
		perm: "can_view_reports",
	},
	{
		to: "/dashboards",
		label: "Dashboards",
		icon: "fa-solid fa-chart-bar",
		color: "var(--c-red)",
		perm: "can_view_dashboards",
	},
	{
		to: "/tethers",
		label: "Tethers",
		icon: "fa-solid fa-diagram-project",
		color: "var(--c-pink)",
		perm: "can_view_tethers",
	},
] as const;

export function Navbar() {
	const { user, logout } = useAuth();
	const { theme, toggle } = useTheme();
	const [menuOpen, setMenuOpen] = useState(false);
	const dropdownRef = useRef<HTMLDivElement>(null);
	const agentQuery = useQuery({
		queryKey: ["chat", "agent-status"],
		queryFn: getAgentStatus,
		refetchInterval: 20000,
		enabled: !!user,
	});

	useEffect(() => {
		function close(event: MouseEvent) {
			if (!dropdownRef.current?.contains(event.target as Node)) {
				setMenuOpen(false);
			}
		}
		document.addEventListener("click", close);
		return () => document.removeEventListener("click", close);
	}, []);

	const location = useLocation();
	const activeColor =
		NAV_LINKS.find((l) => location.pathname.startsWith(l.to))?.color ??
		"var(--c-cyan)";

	if (!user) {
		return null;
	}
	const perms = user.permissions;

	return (
		<header className="top-navbar">
			<div className="nav-container">
				<NavLink to="/" className="nav-brand">
					<div className="nav-logo">
						<img src="/images/tetherdust.png" alt="TetherDust" />
					</div>
					<span className="nav-title">
						Tether
						<span className="accent" style={{ color: activeColor }}>
							Dust
						</span>
					</span>
				</NavLink>

				<nav className="nav-links">
					{NAV_LINKS.filter((l) => perms[l.perm]).map((l) => (
						<NavLink
							key={l.to}
							to={l.to}
							className={({ isActive }) =>
								isActive ? "nav-link-btn active" : "nav-link-btn"
							}
							style={{ "--link-color": l.color } as React.CSSProperties}
						>
							<i className={l.icon} />
							<span>{l.label}</span>
						</NavLink>
					))}
				</nav>

				<div className="nav-actions">
					<div className="user-dropdown" ref={dropdownRef}>
						<button
							type="button"
							className="user-dropdown__trigger"
							aria-label="User menu"
							onClick={() => setMenuOpen((open) => !open)}
						>
							<i className="fa-solid fa-circle-user" />
						</button>
						<div
							className={
								menuOpen ? "user-dropdown__menu is-open" : "user-dropdown__menu"
							}
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
							{user.is_staff && (
								<NavLink to="/admin" className="user-dropdown__item">
									<i className="fa-solid fa-sliders" />
									<span>Control</span>
								</NavLink>
							)}
							<button
								type="button"
								className="user-dropdown__item"
								onClick={toggle}
								aria-label="Toggle dark mode"
							>
								<i
									className={
										theme === "dark" ? "fa-solid fa-sun" : "fa-solid fa-moon"
									}
								/>
								<span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>
							</button>
							<button
								type="button"
								className="user-dropdown__item"
								onClick={() => void logout()}
							>
								<i className="fa-solid fa-right-from-bracket" />
								<span>Logout</span>
							</button>
						</div>
					</div>
				</div>
			</div>
		</header>
	);
}
