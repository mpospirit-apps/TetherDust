import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../hooks/useTheme";

interface SidebarItem {
	to: string;
	label: string;
	icon: string;
	end?: boolean;
}
interface SidebarSection {
	heading: string;
	items: SidebarItem[];
}

const SIDEBAR: SidebarSection[] = [
	{
		heading: "Overview",
		items: [
			{
				to: "/admin",
				label: "Mission Control",
				icon: "fa-gauge-high",
				end: true,
			},
			{ to: "/admin/version", label: "Version", icon: "fa-code-compare" },
		],
	},
	{
		heading: "Configuration",
		items: [
			{ to: "/admin/databases", label: "Databases", icon: "fa-database" },
			{ to: "/admin/codebases", label: "Codebases", icon: "fa-code-branch" },
			{ to: "/admin/docsources", label: "Documentations", icon: "fa-book" },
			{ to: "/admin/mcp-servers", label: "MCP Servers", icon: "fa-server" },
			{ to: "/admin/agents", label: "Agents", icon: "fa-robot" },
			{ to: "/admin/reports", label: "Reports", icon: "fa-table-list" },
			{ to: "/admin/dashboards", label: "Dashboards", icon: "fa-chart-bar" },
			{ to: "/admin/tethers", label: "Tethers", icon: "fa-diagram-project" },
			{ to: "/admin/settings", label: "Settings", icon: "fa-gear" },
		],
	},
	{
		heading: "Access Control",
		items: [
			{ to: "/admin/roles", label: "Roles", icon: "fa-shield-halved" },
			{ to: "/admin/users", label: "Users", icon: "fa-users" },
		],
	},
	{
		heading: "Monitoring",
		items: [
			{
				to: "/admin/report-runs",
				label: "Report Runs",
				icon: "fa-clock-rotate-left",
			},
			{
				to: "/admin/docgen-logs",
				label: "Doc Generation",
				icon: "fa-file-circle-check",
			},
			{
				to: "/admin/chartgen-logs",
				label: "Chart Generation",
				icon: "fa-chart-pie",
			},
			{ to: "/admin/audit", label: "Audit Log", icon: "fa-list-check" },
			{ to: "/admin/sessions", label: "Sessions", icon: "fa-comments" },
		],
	},
];

const NAV_LINKS = [
	{
		to: "/chat",
		label: "Chat",
		icon: "fa-solid fa-comments",
		color: "var(--c-cyan)",
	},
	{
		to: "/docs",
		label: "Docs",
		icon: "fa-solid fa-file-lines",
		color: "var(--c-lime)",
	},
	{
		to: "/reports",
		label: "Reports",
		icon: "fa-solid fa-table-list",
		color: "var(--c-orange)",
	},
	{
		to: "/dashboards",
		label: "Dashboards",
		icon: "fa-solid fa-chart-bar",
		color: "var(--c-red)",
	},
	{
		to: "/tethers",
		label: "Tethers",
		icon: "fa-solid fa-diagram-project",
		color: "var(--c-pink)",
	},
] as const;

function sidebarClass({ isActive }: { isActive: boolean }): string {
	return isActive ? "sidebar-link active" : "sidebar-link";
}

export function AdminLayout() {
	const { user, logout } = useAuth();
	const { theme, toggle } = useTheme();
	const location = useLocation();
	const activeColor =
		NAV_LINKS.find((l) => location.pathname.startsWith(l.to))?.color ??
		"var(--c-pink)"; /* /admin routes fall back to Control pink */
	const [menuOpen, setMenuOpen] = useState(false);
	const dropdownRef = useRef<HTMLDivElement>(null);
	const menuRef = useRef<HTMLDivElement>(null);
	const [menuPos, setMenuPos] = useState<{ top: number; right: number } | null>(
		null,
	);

	useEffect(() => {
		document.body.classList.add("aurora-bg");
		return () => document.body.classList.remove("aurora-bg");
	}, []);

	// Portaled to <body> so the menu escapes the navbar's backdrop-filter
	// "backdrop root" — a nested backdrop-filter can't blur the page behind it.
	function toggleMenu() {
		if (!menuOpen) {
			const rect = dropdownRef.current?.getBoundingClientRect();
			if (rect) {
				setMenuPos({
					top: rect.bottom + 8,
					right: window.innerWidth - rect.right,
				});
			}
		}
		setMenuOpen((open) => !open);
	}

	useEffect(() => {
		function close(event: MouseEvent) {
			const target = event.target as Node;
			if (
				!dropdownRef.current?.contains(target) &&
				!menuRef.current?.contains(target)
			) {
				setMenuOpen(false);
			}
		}
		document.addEventListener("click", close);
		return () => document.removeEventListener("click", close);
	}, []);

	if (!user) {
		return null;
	}
	return (
		<>
			<header className="top-navbar">
				<div className="nav-container">
					<NavLink to="/admin" className="nav-brand">
						<div className="nav-logo">
							<img src="/images/tetherdust.png" alt="TetherDust" />
						</div>
						<div className="nav-brand-text">
							<span className="nav-title">
								Tether
								<span className="accent" style={{ color: activeColor }}>
									Dust
								</span>
							</span>
							<span className="nav-subtitle">Admin Panel</span>
						</div>
					</NavLink>

					<nav className="nav-links">
						{NAV_LINKS.map((l) => (
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
								onClick={toggleMenu}
							>
								<i className="fa-solid fa-bars" />
							</button>
						</div>
					</div>
				</div>
			</header>

			{menuOpen &&
				menuPos &&
				createPortal(
					<div
						className="user-dropdown__menu is-open"
						ref={menuRef}
						style={{
							position: "fixed",
							top: menuPos.top,
							right: menuPos.right,
						}}
					>
						<span className="user-dropdown__username">{user.username}</span>
						<div className="user-dropdown__divider" />
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
					</div>,
					document.body,
				)}

			<aside className="admin-sidebar">
				{SIDEBAR.map((section) => (
					<div className="sidebar-section" key={section.heading}>
						<div className="sidebar-heading">{section.heading}</div>
						{section.items.map((item) => (
							<NavLink
								key={item.to}
								to={item.to}
								end={item.end}
								className={sidebarClass}
							>
								<span className="icon">
									<i className={`fa-solid ${item.icon}`} />
								</span>{" "}
								{item.label}
							</NavLink>
						))}
					</div>
				))}
			</aside>

			<main className="admin-main">
				<Outlet />
			</main>
		</>
	);
}
