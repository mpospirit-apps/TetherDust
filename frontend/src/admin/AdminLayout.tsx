import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
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

// Mirrors the legacy management sidebar. Sections light up as feature verticals land;
// unbuilt targets fall through to the admin placeholder route.
const SIDEBAR: SidebarSection[] = [
	{
		heading: "Overview",
		items: [
			{ to: "/admin", label: "Dashboard", icon: "fa-gauge-high", end: true },
			{ to: "/admin/version", label: "Version", icon: "fa-code-compare" },
		],
	},
	{
		heading: "Configuration",
		items: [
			{ to: "/admin/databases", label: "Databases", icon: "fa-database" },
			{ to: "/admin/codebases", label: "Codebases", icon: "fa-code-branch" },
			{ to: "/admin/docsources", label: "Documentation", icon: "fa-book" },
			{ to: "/admin/mcp-servers", label: "MCP Servers", icon: "fa-server" },
			{ to: "/admin/agents", label: "Agents", icon: "fa-robot" },
			{ to: "/admin/reports", label: "Reports", icon: "fa-chart-bar" },
			{ to: "/admin/dashboards", label: "Dashboards", icon: "fa-gauge" },
			{ to: "/admin/tethers", label: "Tethers", icon: "fa-link" },
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

function sidebarClass({ isActive }: { isActive: boolean }): string {
	return isActive ? "sidebar-link active" : "sidebar-link";
}

export function AdminLayout() {
	const { user, logout } = useAuth();
	const { theme, toggle } = useTheme();
	const [menuOpen, setMenuOpen] = useState(false);
	const dropdownRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		document.body.classList.add("aurora-bg");
		return () => document.body.classList.remove("aurora-bg");
	}, []);

	useEffect(() => {
		function close(event: MouseEvent) {
			if (!dropdownRef.current?.contains(event.target as Node)) {
				setMenuOpen(false);
			}
		}
		document.addEventListener("click", close);
		return () => document.removeEventListener("click", close);
	}, []);

	if (!user) {
		return null;
	}
	const perms = user.permissions;

	return (
		<>
			<nav className="admin-navbar">
				<NavLink to="/admin" className="brand">
					<img
						src="/images/tetherdust.png"
						alt="TetherDust"
						className="brand-icon"
					/>
					<span className="brand-text">
						Tether<span>Dust</span>
					</span>
				</NavLink>
				<div className="nav-right">
					{perms.can_chat && (
						<NavLink to="/chat" className="nav-link">
							Chat
						</NavLink>
					)}
					{perms.can_view_docs && (
						<NavLink to="/docs" className="nav-link">
							Docs
						</NavLink>
					)}
					{perms.can_view_reports && (
						<NavLink to="/reports" className="nav-link">
							Reports
						</NavLink>
					)}
					{perms.can_view_dashboards && (
						<NavLink to="/dashboards" className="nav-link">
							Dashboards
						</NavLink>
					)}
					{perms.can_view_tethers && (
						<NavLink to="/tethers" className="nav-link">
							Tethers
						</NavLink>
					)}
					<NavLink to="/admin" className="nav-link active">
						Control
					</NavLink>
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
			</nav>

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
