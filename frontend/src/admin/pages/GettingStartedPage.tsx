import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, type ReactElement, useState } from "react";
import { Link } from "react-router-dom";
import {
	listAgents,
	listDatabases,
	listRoles,
	listUsers,
} from "../../api/admin";
import { listDashboards } from "../../api/dashboards";
import { listDocSources } from "../../api/docs";
import { listMCPPrompts, listMCPServers } from "../../api/mcp";
import { listReports } from "../../api/reports";
import { listCodebases, listTethers } from "../../api/tethers";
import { WizardSectionHeading, type WizardStepDef } from "../components/wizard";

const STEPS: WizardStepDef[] = [
	{
		key: "agent",
		label: "Configure an Agent",
		description:
			"Set up and activate the AI agent that powers chat, docs, and dashboard generation.",
	},
	{
		key: "codebase",
		label: "Create a Codebase Connection",
		description:
			"Point the agent at your source code so it can browse it while answering questions.",
	},
	{
		key: "documentation",
		label: "Document the Codebase",
		description:
			"Generate a documentation library so the agent understands your codebase's structure and conventions.",
	},
	{
		key: "database",
		label: "Create a Database Connection",
		description:
			"Connect a target database so the agent can query it and answer questions about your data.",
	},
	{
		key: "database-documentation",
		label: "Document the Database",
		description:
			"Generate a documentation library from the database so the agent understands table schemas and business context.",
	},
	{
		key: "tethers",
		label: "Create a Tether",
		description:
			"Link a codebase to a database so the agent can map code to the data it reads and writes.",
	},
];

const ROLE_STEPS: WizardStepDef[] = [
	{
		key: "role",
		label: "Create a Role",
		description:
			"Define what a group of users is allowed to see and do inside TetherDust.",
	},
	{
		key: "assign-role",
		label: "Assign a Role to a User",
		description: "Give a user account the permissions defined by that role.",
	},
];

const ANALYTICS_STEPS: WizardStepDef[] = [
	{
		key: "report",
		label: "Create a Report",
		description:
			"Turn a SQL query into a report you can run on demand or on a schedule.",
	},
	{
		key: "dashboard",
		label: "Create a Dashboard",
		description:
			"Build or generate a dashboard of charts to visualize your data.",
	},
];

const ADVANCED_STEPS: WizardStepDef[] = [
	{
		key: "mcp-prompt",
		label: "Create a Prompt",
		description:
			"Add a reusable prompt template to the built-in MCP server to give the agent extra guidance on demand.",
	},
	{
		key: "mcp-server",
		label: "Register an MCP Server",
		description: "Extend the agent with custom tools from your own MCP server.",
	},
];

const TABS = [
	{ key: "welcome", label: "Welcome" },
	{ key: "foundations", label: "Foundations" },
	{ key: "analytics", label: "Analytics" },
	{ key: "roles", label: "Role Management" },
	{ key: "advanced", label: "Advanced" },
] as const;
type TabKey = (typeof TABS)[number]["key"];

function StepAction({
	complete,
	to,
	icon,
	label,
}: {
	complete: boolean;
	to: string;
	icon: string;
	label: string;
}) {
	if (complete) {
		return (
			<span className="btn btn-completed">
				<i className="fa-solid fa-circle-check" /> Completed
			</span>
		);
	}
	return (
		<Link to={to} className="btn btn-primary">
			<i className={`fa-solid ${icon}`} /> {label}
		</Link>
	);
}

function WelcomeTab({ onGetStarted }: { onGetStarted: () => void }) {
	return (
		<div className="card">
			<p>
				<strong>TetherDust</strong> is a multi-agent AI database querying
				system. Ask questions about your data in plain English through chat, and
				an AI agent (Codex CLI or Claude Code CLI) uses MCP tools to explore
				your databases, codebases, and documentation to answer them — no SQL
				required.
			</p>
			<p style={{ marginTop: "var(--md)" }}>
				Beyond chat, the same agent writes documentation, builds scheduled
				reports, generates chart dashboards, and maps your codebase to the
				databases it touches. Role-based access control gates all of it, so each
				user only sees the tools, data, and pages they're permitted to use.
			</p>
			<p style={{ marginTop: "var(--md)" }}>
				Get started with the{" "}
				<button
					type="button"
					onClick={onGetStarted}
					style={{
						background: "none",
						border: "none",
						padding: 0,
						font: "inherit",
						fontWeight: 700,
						color: "var(--c-cyan)",
						textDecoration: "underline",
						cursor: "pointer",
					}}
				>
					Foundations
				</button>
				.
			</p>
		</div>
	);
}

// Five main sections the agent powers, placed clockwise from the top around
// a regular pentagon. nx/ny are the precomputed cos/sin of each spoke's
// angle, used to offset each node from the center by --star-radius in CSS.
// Colors match each section's own accent in the main nav (see Navbar.tsx).
const AGENT_STAR_NODES = [
	{
		key: "chat",
		label: "Chat",
		icon: "fa-comments",
		angle: -90,
		nx: 0,
		ny: -1,
		color: "var(--c-cyan)",
	},
	{
		key: "docs",
		label: "Docs",
		icon: "fa-file-lines",
		angle: -18,
		nx: 0.951,
		ny: -0.309,
		color: "var(--c-lime)",
	},
	{
		key: "reports",
		label: "Reports",
		icon: "fa-table-list",
		angle: 54,
		nx: 0.588,
		ny: 0.809,
		color: "var(--c-orange)",
	},
	{
		key: "dashboards",
		label: "Dashboards",
		icon: "fa-chart-bar",
		angle: 126,
		nx: -0.588,
		ny: 0.809,
		color: "var(--c-red)",
	},
	{
		key: "tethers",
		label: "Tethers",
		icon: "fa-diagram-project",
		angle: 198,
		nx: -0.951,
		ny: -0.309,
		color: "var(--c-pink)",
	},
] as const;

function AgentStarDiagram() {
	return (
		<div className="agent-star">
			{AGENT_STAR_NODES.map((node) => (
				<div
					key={node.key}
					className="agent-star__spoke"
					style={{ "--angle": `${node.angle}deg` } as CSSProperties}
				/>
			))}
			<div className="agent-star__center">
				<div className="doc-hiw-icon agent-star__center-icon">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="agent-star__label">Agent</div>
			</div>
			{AGENT_STAR_NODES.map((node) => (
				<div
					key={node.key}
					className="agent-star__node"
					style={
						{
							"--nx": node.nx,
							"--ny": node.ny,
							"--bubble": node.color,
						} as CSSProperties
					}
				>
					<div className="doc-hiw-icon agent-star__node-icon">
						<i className={`fa-solid ${node.icon}`} />
					</div>
					<div className="agent-star__label">{node.label}</div>
				</div>
			))}
		</div>
	);
}

function CodebaseConnectionDiagram() {
	return (
		<div className="codebase-flow">
			<svg viewBox="0 0 400 220" className="codebase-flow__svg">
				<title>Codebase Connection Flow</title>
				<path
					d="M 40,40 C 120,40 120,110 200,110"
					className="codebase-flow__line"
				/>
				<path d="M 40,110 L 200,110" className="codebase-flow__line" />
				<path
					d="M 40,180 C 120,180 120,110 200,110"
					className="codebase-flow__line"
				/>
				<path d="M 200,110 L 348,110" className="codebase-flow__line-agent" />
			</svg>

			<div className="codebase-flow__node codebase-flow__node--github">
				<div className="doc-hiw-icon codebase-flow__icon codebase-flow__icon--github">
					<i className="fa-brands fa-github" />
				</div>
				<div className="codebase-flow__label">GitHub</div>
			</div>

			<div className="codebase-flow__node codebase-flow__node--gitlab">
				<div className="doc-hiw-icon codebase-flow__icon codebase-flow__icon--gitlab">
					<i className="fa-brands fa-gitlab" />
				</div>
				<div className="codebase-flow__label">GitLab</div>
			</div>

			<div className="codebase-flow__node codebase-flow__node--local">
				<div className="doc-hiw-icon codebase-flow__icon codebase-flow__icon--local">
					<i className="fa-solid fa-folder-open" />
				</div>
				<div className="codebase-flow__label">Local Folder</div>
			</div>

			<div className="codebase-flow__node codebase-flow__node--hub">
				<div className="doc-hiw-icon codebase-flow__icon codebase-flow__icon--hub">
					<i className="fa-solid fa-code-branch" />
				</div>
				<div className="codebase-flow__label">Connection</div>
			</div>

			<div className="codebase-flow__node codebase-flow__node--agent">
				<div className="doc-hiw-icon codebase-flow__icon codebase-flow__icon--agent">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="codebase-flow__label">Agent</div>
			</div>
		</div>
	);
}

function CodebaseDocsDiagram() {
	return (
		<div className="docs-flow">
			<svg viewBox="0 0 400 220" className="docs-flow__svg">
				<title>Codebase Documentation Flow</title>
				<path
					d="M 40,40 C 120,40 120,110 200,110"
					className="docs-flow__line-left"
				/>
				<path d="M 40,110 L 200,110" className="docs-flow__line-left" />
				<path
					d="M 40,180 C 120,180 120,110 200,110"
					className="docs-flow__line-left"
				/>
				<path
					d="M 200,110 C 280,110 280,40 360,40"
					className="docs-flow__line-right"
				/>
				<path d="M 200,110 L 360,110" className="docs-flow__line-right" />
				<path
					d="M 200,110 C 280,110 280,180 360,180"
					className="docs-flow__line-right"
				/>
			</svg>

			<div className="docs-flow__node docs-flow__node--code1">
				<div className="doc-hiw-icon docs-flow__icon docs-flow__icon--code">
					<i className="fa-solid fa-file-code" />
				</div>
				<div className="docs-flow__label">main.py</div>
			</div>

			<div className="docs-flow__node docs-flow__node--code2">
				<div className="doc-hiw-icon docs-flow__icon docs-flow__icon--code">
					<i className="fa-solid fa-file-code" />
				</div>
				<div className="docs-flow__label">utils.ts</div>
			</div>

			<div className="docs-flow__node docs-flow__node--code3">
				<div className="doc-hiw-icon docs-flow__icon docs-flow__icon--code">
					<i className="fa-solid fa-file-code" />
				</div>
				<div className="docs-flow__label">api.go</div>
			</div>

			<div className="docs-flow__node docs-flow__node--agent">
				<div className="doc-hiw-icon docs-flow__icon docs-flow__icon--agent">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="docs-flow__label">Agent</div>
			</div>

			<div className="docs-flow__node docs-flow__node--doc1">
				<div className="doc-hiw-icon docs-flow__icon docs-flow__icon--doc">
					<i className="fa-solid fa-file-lines" />
				</div>
				<div className="docs-flow__label">overview.md</div>
			</div>

			<div className="docs-flow__node docs-flow__node--doc2">
				<div className="doc-hiw-icon docs-flow__icon docs-flow__icon--doc">
					<i className="fa-solid fa-file-lines" />
				</div>
				<div className="docs-flow__label">modules.md</div>
			</div>

			<div className="docs-flow__node docs-flow__node--doc3">
				<div className="doc-hiw-icon docs-flow__icon docs-flow__icon--doc">
					<i className="fa-solid fa-file-lines" />
				</div>
				<div className="docs-flow__label">api.md</div>
			</div>
		</div>
	);
}

function DatabaseConnectionDiagram() {
	return (
		<div className="database-flow">
			<svg viewBox="0 0 400 220" className="database-flow__svg">
				<title>Database Connection Flow</title>
				<path
					d="M 40,40 C 120,40 120,110 200,110"
					className="database-flow__line"
				/>
				<path d="M 40,110 L 200,110" className="database-flow__line" />
				<path
					d="M 40,180 C 120,180 120,110 200,110"
					className="database-flow__line"
				/>
				<path d="M 200,110 L 348,110" className="database-flow__line-agent" />
			</svg>

			<div className="database-flow__node database-flow__node--postgres">
				<div className="doc-hiw-icon database-flow__icon database-flow__icon--postgres">
					<i className="fa-solid fa-database" />
				</div>
				<div className="database-flow__label">PostgreSQL</div>
			</div>

			<div className="database-flow__node database-flow__node--mysql">
				<div className="doc-hiw-icon database-flow__icon database-flow__icon--mysql">
					<i className="fa-solid fa-database" />
				</div>
				<div className="database-flow__label">MySQL</div>
			</div>

			<div className="database-flow__node database-flow__node--snowflake">
				<div className="doc-hiw-icon database-flow__icon database-flow__icon--snowflake">
					<i className="fa-solid fa-snowflake" />
				</div>
				<div className="database-flow__label">Snowflake</div>
			</div>

			<div className="database-flow__node database-flow__node--hub">
				<div className="doc-hiw-icon database-flow__icon database-flow__icon--hub">
					<i className="fa-solid fa-plug" />
				</div>
				<div className="database-flow__label">Connection</div>
			</div>

			<div className="database-flow__node database-flow__node--agent">
				<div className="doc-hiw-icon database-flow__icon database-flow__icon--agent">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="database-flow__label">Agent</div>
			</div>
		</div>
	);
}

function DatabaseDocsDiagram() {
	return (
		<div className="db-docs-flow">
			<svg viewBox="0 0 400 220" className="db-docs-flow__svg">
				<title>Database Documentation Flow</title>
				<path
					d="M 40,40 C 120,40 120,110 200,110"
					className="db-docs-flow__line-left"
				/>
				<path d="M 40,110 L 200,110" className="db-docs-flow__line-left" />
				<path
					d="M 40,180 C 120,180 120,110 200,110"
					className="db-docs-flow__line-left"
				/>
				<path
					d="M 200,110 C 280,110 280,40 360,40"
					className="db-docs-flow__line-right"
				/>
				<path d="M 200,110 L 360,110" className="db-docs-flow__line-right" />
				<path
					d="M 200,110 C 280,110 280,180 360,180"
					className="db-docs-flow__line-right"
				/>
			</svg>

			<div className="db-docs-flow__node db-docs-flow__node--db">
				<div className="doc-hiw-icon db-docs-flow__icon db-docs-flow__icon--db">
					<i className="fa-solid fa-database" />
				</div>
				<div className="db-docs-flow__label">Database</div>
			</div>

			<div className="db-docs-flow__node db-docs-flow__node--codebase">
				<div className="doc-hiw-icon db-docs-flow__icon db-docs-flow__icon--codebase">
					<i className="fa-solid fa-code-branch" />
				</div>
				<div className="db-docs-flow__label">Codebase</div>
			</div>

			<div className="db-docs-flow__node db-docs-flow__node--codedocs">
				<div className="doc-hiw-icon db-docs-flow__icon db-docs-flow__icon--codedocs">
					<i className="fa-solid fa-book-open" />
				</div>
				<div className="db-docs-flow__label">Codebase Docs</div>
			</div>

			<div className="db-docs-flow__node db-docs-flow__node--agent">
				<div className="doc-hiw-icon db-docs-flow__icon db-docs-flow__icon--agent">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="db-docs-flow__label">Agent</div>
			</div>

			<div className="db-docs-flow__node db-docs-flow__node--doc1">
				<div className="doc-hiw-icon db-docs-flow__icon db-docs-flow__icon--doc">
					<i className="fa-solid fa-file-lines" />
				</div>
				<div className="db-docs-flow__label">users.md</div>
			</div>

			<div className="db-docs-flow__node db-docs-flow__node--doc2">
				<div className="doc-hiw-icon db-docs-flow__icon db-docs-flow__icon--doc">
					<i className="fa-solid fa-file-lines" />
				</div>
				<div className="db-docs-flow__label">orders.md</div>
			</div>

			<div className="db-docs-flow__node db-docs-flow__node--doc3">
				<div className="doc-hiw-icon db-docs-flow__icon db-docs-flow__icon--doc">
					<i className="fa-solid fa-file-lines" />
				</div>
				<div className="db-docs-flow__label">products.md</div>
			</div>
		</div>
	);
}

function TetherConnectionDiagram() {
	return (
		<div className="tether-flow">
			<svg viewBox="0 0 400 220" className="tether-flow__svg">
				<title>Tether Connection Flow</title>
				<path d="M 60,60 L 200,60" className="tether-flow__line-bridge" />
				<path d="M 340,60 L 200,60" className="tether-flow__line-bridge" />
				<path d="M 200,158 L 200,60" className="tether-flow__line-agent" />
			</svg>

			<div className="tether-flow__node tether-flow__node--codebase">
				<div className="doc-hiw-icon tether-flow__icon tether-flow__icon--codebase">
					<i className="fa-solid fa-code-branch" />
				</div>
				<div className="tether-flow__label">Codebase</div>
			</div>

			<div className="tether-flow__node tether-flow__node--database">
				<div className="doc-hiw-icon tether-flow__icon tether-flow__icon--database">
					<i className="fa-solid fa-database" />
				</div>
				<div className="tether-flow__label">Database</div>
			</div>

			<div className="tether-flow__node tether-flow__node--tether">
				<div className="doc-hiw-icon tether-flow__icon tether-flow__icon--tether">
					<i className="fa-solid fa-diagram-project" />
				</div>
				<div className="tether-flow__label">Tether</div>
			</div>

			<div className="tether-flow__node tether-flow__node--agent">
				<div className="doc-hiw-icon tether-flow__icon tether-flow__icon--agent">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="tether-flow__label">Agent</div>
			</div>
		</div>
	);
}

function ReportDiagram() {
	return (
		<div className="report-flow">
			<svg viewBox="0 0 400 220" className="report-flow__svg">
				<title>Report Flow Diagram</title>
				<path
					d="M 60,60 C 130,60 130,110 200,110"
					className="report-flow__line-left"
				/>
				<path
					d="M 60,140 C 130,140 130,110 200,110"
					className="report-flow__line-left"
				/>
				<path
					d="M 200,110 C 270,110 270,60 340,60"
					className="report-flow__line-right"
				/>
				<path
					d="M 200,110 C 270,110 270,140 340,140"
					className="report-flow__line-right"
				/>
			</svg>

			<div className="report-flow__node report-flow__node--sql">
				<div className="doc-hiw-icon report-flow__icon report-flow__icon--sql">
					<i className="fa-solid fa-scroll" />
				</div>
				<div className="report-flow__label">Saved SQL</div>
			</div>

			<div className="report-flow__node report-flow__node--schedule">
				<div className="doc-hiw-icon report-flow__icon report-flow__icon--schedule">
					<i className="fa-solid fa-clock" />
				</div>
				<div className="report-flow__label">Schedule</div>
			</div>

			<div className="report-flow__node report-flow__node--worker">
				<div className="doc-hiw-icon report-flow__icon report-flow__icon--worker">
					<i className="fa-solid fa-gears" />
				</div>
				<div className="report-flow__label">Celery Worker</div>
			</div>

			<div className="report-flow__node report-flow__node--inapp">
				<div className="doc-hiw-icon report-flow__icon report-flow__icon--inapp">
					<i className="fa-solid fa-bell" />
				</div>
				<div className="report-flow__label">In-App</div>
			</div>

			<div className="report-flow__node report-flow__node--email">
				<div className="doc-hiw-icon report-flow__icon report-flow__icon--email">
					<i className="fa-solid fa-envelope" />
				</div>
				<div className="report-flow__label">Email</div>
			</div>
		</div>
	);
}

function DashboardDiagram() {
	return (
		<div className="dashboard-flow">
			<svg viewBox="0 0 460 220" className="dashboard-flow__svg">
				<title>Dashboard Flow Diagram</title>
				<path
					d="M 40,40 C 102.5,40 102.5,110 165,110"
					className="dashboard-flow__line-left"
				/>
				<path d="M 40,110 L 165,110" className="dashboard-flow__line-left" />
				<path
					d="M 40,180 C 102.5,180 102.5,110 165,110"
					className="dashboard-flow__line-left"
				/>
				<path
					d="M 165,110 C 225,110 225,40 285,40"
					className="dashboard-flow__line-right"
				/>
				<path d="M 165,110 L 285,110" className="dashboard-flow__line-right" />
				<path
					d="M 165,110 C 225,110 225,180 285,180"
					className="dashboard-flow__line-right"
				/>
				<path
					d="M 285,40 C 348.5,40 348.5,110 412,110"
					className="dashboard-flow__line-right"
				/>
				<path d="M 285,110 L 412,110" className="dashboard-flow__line-right" />
				<path
					d="M 285,180 C 348.5,180 348.5,110 412,110"
					className="dashboard-flow__line-right"
				/>
			</svg>

			{/* Column 1: Sources */}
			<div className="dashboard-flow__node dashboard-flow__node--db">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--db">
					<i className="fa-solid fa-database" />
				</div>
				<div className="dashboard-flow__label">Database</div>
			</div>

			<div className="dashboard-flow__node dashboard-flow__node--codebase">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--codebase">
					<i className="fa-solid fa-code-branch" />
				</div>
				<div className="dashboard-flow__label">Codebase</div>
			</div>

			<div className="dashboard-flow__node dashboard-flow__node--docs">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--docs">
					<i className="fa-solid fa-book-open" />
				</div>
				<div className="dashboard-flow__label">Docs</div>
			</div>

			{/* Column 2: Agent */}
			<div className="dashboard-flow__node dashboard-flow__node--agent">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--agent">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="dashboard-flow__label">Agent</div>
			</div>

			{/* Column 3: Visual Charts */}
			<div className="dashboard-flow__node dashboard-flow__node--chart1">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--chart1">
					<i className="fa-solid fa-chart-column" />
				</div>
				<div className="dashboard-flow__label">Bar Chart</div>
			</div>

			<div className="dashboard-flow__node dashboard-flow__node--chart2">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--chart2">
					<i className="fa-solid fa-chart-pie" />
				</div>
				<div className="dashboard-flow__label">Pie Chart</div>
			</div>

			<div className="dashboard-flow__node dashboard-flow__node--chart3">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--chart3">
					<i className="fa-solid fa-chart-line" />
				</div>
				<div className="dashboard-flow__label">Line Chart</div>
			</div>

			<div className="dashboard-flow__node dashboard-flow__node--dashboard">
				<div className="doc-hiw-icon dashboard-flow__icon dashboard-flow__icon--dashboard">
					<i className="fa-solid fa-table-cells-large" />
				</div>
				<div className="dashboard-flow__label">Dashboard</div>
			</div>
		</div>
	);
}

function CreateRoleDiagram() {
	return (
		<div className="role-star">
			<svg viewBox="0 0 400 220" className="role-star__svg">
				<title>Role Permissions Diagram</title>
				<line x1="200" y1="110" x2="80" y2="50" className="role-star__line" />
				<line x1="200" y1="110" x2="320" y2="50" className="role-star__line" />
				<line x1="200" y1="110" x2="80" y2="170" className="role-star__line" />
				<line x1="200" y1="110" x2="320" y2="170" className="role-star__line" />
				<foreignObject x="130" y="70" width="20" height="20">
					<div className="role-star__lock-badge">
						<i className="fa-solid fa-lock" />
					</div>
				</foreignObject>
				<foreignObject x="250" y="70" width="20" height="20">
					<div className="role-star__lock-badge">
						<i className="fa-solid fa-lock" />
					</div>
				</foreignObject>
				<foreignObject x="130" y="130" width="20" height="20">
					<div className="role-star__lock-badge">
						<i className="fa-solid fa-lock" />
					</div>
				</foreignObject>
				<foreignObject x="250" y="130" width="20" height="20">
					<div className="role-star__lock-badge">
						<i className="fa-solid fa-lock" />
					</div>
				</foreignObject>
			</svg>

			{/* Center: Role Key */}
			<div className="role-star__node role-star__node--center">
				<div className="doc-hiw-icon role-star__icon role-star__icon--center">
					<i className="fa-solid fa-key" />
				</div>
				<div className="role-star__label">Role</div>
			</div>

			{/* Spokes */}
			<div className="role-star__node role-star__node--spoke1">
				<div className="doc-hiw-icon role-star__icon role-star__icon--spoke">
					<i className="fa-solid fa-code-branch" />
				</div>
				<div className="role-star__label">Codebases</div>
			</div>

			<div className="role-star__node role-star__node--spoke2">
				<div className="doc-hiw-icon role-star__icon role-star__icon--spoke">
					<i className="fa-solid fa-database" />
				</div>
				<div className="role-star__label">Databases</div>
			</div>

			<div className="role-star__node role-star__node--spoke3">
				<div className="doc-hiw-icon role-star__icon role-star__icon--spoke">
					<i className="fa-solid fa-table-cells-large" />
				</div>
				<div className="role-star__label">Dashboards</div>
			</div>

			<div className="role-star__node role-star__node--spoke4">
				<div className="doc-hiw-icon role-star__icon role-star__icon--spoke">
					<i className="fa-solid fa-gears" />
				</div>
				<div className="role-star__label">MCP Tools</div>
			</div>
		</div>
	);
}

function AssignRoleDiagram() {
	return (
		<div className="user-role-flow">
			<svg viewBox="0 0 400 220" className="user-role-flow__svg">
				<title>User Role Assignment Diagram</title>
				<line
					x1="60"
					y1="110"
					x2="200"
					y2="110"
					className="user-role-flow__line-left"
				/>
				<path
					d="M 200,110 C 270,110 270,40 340,40"
					className="user-role-flow__line-right"
				/>
				<path d="M 200,110 L 340,110" className="user-role-flow__line-right" />
				<path
					d="M 200,110 C 270,110 270,180 340,180"
					className="user-role-flow__line-right"
				/>
			</svg>

			{/* Left Column: User */}
			<div className="user-role-flow__node user-role-flow__node--user">
				<div className="doc-hiw-icon user-role-flow__icon user-role-flow__icon--user">
					<i className="fa-solid fa-user" />
				</div>
				<div className="user-role-flow__label">User</div>
			</div>

			{/* Center: Access Lock */}
			<div className="user-role-flow__node user-role-flow__node--role">
				<div className="doc-hiw-icon user-role-flow__icon user-role-flow__icon--role">
					<i className="fa-solid fa-lock" />
				</div>
				<div className="user-role-flow__label">Access</div>
			</div>

			{/* Right Column: Allowed features */}
			<div className="user-role-flow__node user-role-flow__node--feat1">
				<div className="doc-hiw-icon user-role-flow__icon user-role-flow__icon--feat">
					<i className="fa-solid fa-table-cells-large" />
				</div>
				<div className="user-role-flow__label">Dashboards</div>
			</div>

			<div className="user-role-flow__node user-role-flow__node--feat2">
				<div className="doc-hiw-icon user-role-flow__icon user-role-flow__icon--feat">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="user-role-flow__label">Agent Chat</div>
			</div>

			<div className="user-role-flow__node user-role-flow__node--feat3">
				<div className="doc-hiw-icon user-role-flow__icon user-role-flow__icon--feat">
					<i className="fa-solid fa-database" />
				</div>
				<div className="user-role-flow__label">Databases</div>
			</div>
		</div>
	);
}

function PromptDiagram() {
	return (
		<div className="prompt-flow">
			<svg viewBox="0 0 400 220" className="prompt-flow__svg">
				<title>Prompt Creation Diagram</title>
				<path d="M 60,110 L 200,110" className="prompt-flow__line" />
				<path d="M 200,110 L 340,110" className="prompt-flow__line-agent" />
			</svg>

			<div className="prompt-flow__node prompt-flow__node--user">
				<div className="doc-hiw-icon prompt-flow__icon prompt-flow__icon--user">
					<i className="fa-solid fa-user" />
				</div>
				<div className="prompt-flow__label">User</div>
			</div>

			<div className="prompt-flow__node prompt-flow__node--template">
				<div className="doc-hiw-icon prompt-flow__icon prompt-flow__icon--template">
					<i className="fa-solid fa-scroll" />
				</div>
				<div className="prompt-flow__label">Prompt</div>
			</div>

			<div className="prompt-flow__node prompt-flow__node--agent">
				<div className="doc-hiw-icon prompt-flow__icon prompt-flow__icon--agent">
					<i className="fa-solid fa-robot" />
				</div>
				<div className="prompt-flow__label">Agent</div>
			</div>
		</div>
	);
}

function McpDiagram() {
	return (
		<div className="mcp-flow">
			<svg viewBox="0 0 400 220" className="mcp-flow__svg">
				<title>MCP Server Diagram</title>
				<path
					d="M 60,60 C 130,60 130,110 200,110"
					className="mcp-flow__line-left"
				/>
				<path
					d="M 60,140 C 130,140 130,110 200,110"
					className="mcp-flow__line-left"
				/>
				<path
					d="M 200,110 C 270,110 270,40 340,40"
					className="mcp-flow__line-right"
				/>
				<path d="M 200,110 L 340,110" className="mcp-flow__line-right" />
				<path
					d="M 200,110 C 270,110 270,180 340,180"
					className="mcp-flow__line-right"
				/>
			</svg>

			{/* Column 1: MCP Servers */}
			<div className="mcp-flow__node mcp-flow__node--local">
				<div className="doc-hiw-icon mcp-flow__icon mcp-flow__icon--local">
					<i className="fa-solid fa-terminal" />
				</div>
				<div className="mcp-flow__label">Local Process</div>
			</div>

			<div className="mcp-flow__node mcp-flow__node--remote">
				<div className="doc-hiw-icon mcp-flow__icon mcp-flow__icon--remote">
					<i className="fa-solid fa-globe" />
				</div>
				<div className="mcp-flow__label">Remote HTTP</div>
			</div>

			{/* Column 2: MCP Client / Host */}
			<div className="mcp-flow__node mcp-flow__node--client">
				<div className="doc-hiw-icon mcp-flow__icon mcp-flow__icon--client">
					<i className="fa-solid fa-circle-nodes" />
				</div>
				<div className="mcp-flow__label">Client</div>
			</div>

			{/* Column 3: Exposed Primitives */}
			<div className="mcp-flow__node mcp-flow__node--tools">
				<div className="doc-hiw-icon mcp-flow__icon mcp-flow__icon--tools">
					<i className="fa-solid fa-gears" />
				</div>
				<div className="mcp-flow__label">Tools</div>
			</div>

			<div className="mcp-flow__node mcp-flow__node--resources">
				<div className="doc-hiw-icon mcp-flow__icon mcp-flow__icon--resources">
					<i className="fa-solid fa-database" />
				</div>
				<div className="mcp-flow__label">Resources</div>
			</div>

			<div className="mcp-flow__node mcp-flow__node--prompts">
				<div className="doc-hiw-icon mcp-flow__icon mcp-flow__icon--prompts">
					<i className="fa-solid fa-scroll" />
				</div>
				<div className="mcp-flow__label">Prompts</div>
			</div>
		</div>
	);
}

function FoundationsTab() {
	const { data: agents } = useQuery({
		queryKey: ["admin", "agents"],
		queryFn: listAgents,
	});
	const hasActiveAgent = (agents?.results ?? []).some((a) => a.is_active);

	const { data: codebases } = useQuery({
		queryKey: ["admin", "codebases"],
		queryFn: listCodebases,
	});
	const hasCodebase = (codebases?.count ?? 0) > 0;

	const { data: docSources } = useQuery({
		queryKey: ["admin", "docsources"],
		queryFn: listDocSources,
	});
	const hasCodebaseDocs = (docSources?.results ?? []).some(
		(d) => d.doc_type === "codebase",
	);
	const hasDatabaseDocs = (docSources?.results ?? []).some(
		(d) => d.doc_type === "database",
	);

	const { data: databases } = useQuery({
		queryKey: ["admin", "databases"],
		queryFn: listDatabases,
	});
	const hasDatabase = (databases?.count ?? 0) > 0;

	const { data: tethers } = useQuery({
		queryKey: ["admin", "tethers"],
		queryFn: listTethers,
	});
	const hasTether = (tethers?.count ?? 0) > 0;

	return (
		<>
			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={STEPS[0]} index={0} />
					<StepAction
						complete={hasActiveAgent}
						to="/admin/agents/new"
						icon="fa-robot"
						label="Add Agent"
					/>
				</div>
				<div className="card">
					<AgentStarDiagram />
					<p>
						An <strong>agent</strong> is the AI (Codex CLI or Claude Code CLI)
						that answers chat questions and drives documentation, report, and
						dashboard generation. Add one, provide its credentials, and activate
						it — only one agent can be active at a time.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={STEPS[1]} index={1} />
					<StepAction
						complete={hasCodebase}
						to="/admin/codebases/new"
						icon="fa-code-branch"
						label="Add Codebase"
					/>
				</div>
				<div className="card">
					<CodebaseConnectionDiagram />
					<p>
						A <strong>codebase connection</strong> tells TetherDust where your
						source code lives — a GitHub or GitLab repository (read directly, no
						clone) or a local folder under <code>sources/codebases/</code>. Once
						connected, the agent can browse the codebase on demand to answer
						questions about it, generate documentation, and link it to a
						database as a Tether.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={STEPS[2]} index={2} />
					<StepAction
						complete={hasCodebaseDocs}
						to="/admin/docsources/library"
						icon="fa-book-open"
						label="Generate a Library"
					/>
				</div>
				<div className="card">
					<CodebaseDocsDiagram />
					<p>
						Once a codebase is connected, have the agent read through it and
						write a <strong>documentation library</strong> — a cross-linked tree
						of markdown pages, one per subsystem or module. This gives the agent
						(and your team) a browsable reference instead of re-exploring the
						codebase from scratch on every question.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={STEPS[3]} index={3} />
					<StepAction
						complete={hasDatabase}
						to="/admin/databases/new"
						icon="fa-database"
						label="Add Database"
					/>
				</div>
				<div className="card">
					<DatabaseConnectionDiagram />
					<p>
						A <strong>database connection</strong> gives the agent read access
						to a target database — PostgreSQL, MySQL, SQL Server, ClickHouse,
						Oracle, Snowflake, BigQuery, and more. Once connected, the agent can
						list tables, inspect schemas, and run queries to answer
						natural-language questions about your data.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={STEPS[4]} index={4} />
					<StepAction
						complete={hasDatabaseDocs}
						to="/admin/docsources/library"
						icon="fa-book-open"
						label="Generate a Library"
					/>
				</div>
				<div className="card">
					<DatabaseDocsDiagram />
					<p>
						Once a database is connected, have the agent read through its schema
						and write a <strong>documentation library</strong> — table-by-table
						descriptions, relationships, and business context. This gives the
						agent grounded knowledge instead of guessing at column meanings from
						names alone.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={STEPS[5]} index={5} />
					<StepAction
						complete={hasTether}
						to="/admin/tethers/new"
						icon="fa-diagram-project"
						label="Add Tether"
					/>
				</div>
				<div className="card">
					<TetherConnectionDiagram />
					<p>
						A <strong>Tether</strong> links one codebase to one database and
						stores an AI-generated, versioned graph mapping code to the data it
						touches — models, queries, and read/write paths. This helps the
						agent (and your team) trace how a table is actually used across the
						codebase.
					</p>
				</div>
			</div>
		</>
	);
}

function RoleManagementTab() {
	const { data: roles } = useQuery({
		queryKey: ["admin", "roles"],
		queryFn: listRoles,
	});
	const hasRole = (roles?.count ?? 0) > 0;

	const { data: users } = useQuery({
		queryKey: ["admin", "users"],
		queryFn: listUsers,
	});
	const hasAssignedRole = (users?.results ?? []).some((u) => u.role !== null);

	return (
		<>
			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={ROLE_STEPS[0]} index={0} />
					<StepAction
						complete={hasRole}
						to="/admin/roles/new"
						icon="fa-shield-halved"
						label="Add Role"
					/>
				</div>
				<div className="card">
					<CreateRoleDiagram />
					<p>
						A <strong>role</strong> controls what its users can access: which
						tools, databases, documentation sources, codebases, prompts, and MCP
						servers they're allowed to use, a max row limit on query results,
						and whether they can chat, view reports, dashboards, or tethers. An{" "}
						<strong>admin role</strong> bypasses all restrictions — staff users
						are always unrestricted regardless of role.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={ROLE_STEPS[1]} index={1} />
					<StepAction
						complete={hasAssignedRole}
						to="/admin/users/new"
						icon="fa-users"
						label="Add User"
					/>
				</div>
				<div className="card">
					<AssignRoleDiagram />
					<p>
						Every non-staff <strong>user</strong> needs a role to access
						anything beyond logging in. Create or edit a user and assign one of
						your roles to grant it that role's tools, data, and page access.
					</p>
				</div>
			</div>
		</>
	);
}

function AnalyticsTab() {
	const { data: reports } = useQuery({
		queryKey: ["admin", "reports"],
		queryFn: listReports,
	});
	const hasReport = (reports?.count ?? 0) > 0;

	const { data: dashboards } = useQuery({
		queryKey: ["admin", "dashboards"],
		queryFn: listDashboards,
	});
	const hasDashboard = (dashboards?.count ?? 0) > 0;

	return (
		<>
			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={ANALYTICS_STEPS[0]} index={0} />
					<StepAction
						complete={hasReport}
						to="/admin/reports/new"
						icon="fa-table-list"
						label="Add Report"
					/>
				</div>
				<div className="card">
					<ReportDiagram />
					<p>
						A <strong>report</strong> is a saved SQL query that runs manually or
						on a schedule (interval, daily, weekly, monthly) and delivers its
						results in-app or by email. Executions run async on a Celery worker,
						so long queries don't block anything.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={ANALYTICS_STEPS[1]} index={1} />
					<StepAction
						complete={hasDashboard}
						to="/admin/dashboards/add"
						icon="fa-chart-bar"
						label="Add Dashboard"
					/>
				</div>
				<div className="card">
					<DashboardDiagram />
					<p>
						A <strong>dashboard</strong> is a collection of charts — build one
						manually chart-by-chart, or let the agent explore your data and
						generate a full set of charts for you.
					</p>
				</div>
			</div>
		</>
	);
}

function AdvancedTab() {
	const { data: mcpServers } = useQuery({
		queryKey: ["admin", "mcp-servers"],
		queryFn: listMCPServers,
	});
	const hasCustomServer = (mcpServers?.results ?? []).some(
		(s) => !s.is_builtin,
	);

	const builtinServer = (mcpServers?.results ?? []).find((s) => s.is_builtin);
	const { data: builtinPrompts } = useQuery({
		queryKey: ["admin", "mcp-prompts", builtinServer?.id],
		queryFn: () => listMCPPrompts(builtinServer?.id ?? ""),
		enabled: !!builtinServer,
	});
	const hasPrompt = (builtinPrompts?.results ?? []).length > 0;

	return (
		<>
			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={ADVANCED_STEPS[0]} index={0} />
					<StepAction
						complete={hasPrompt}
						to={
							builtinServer
								? `/admin/mcp-servers/${builtinServer.id}`
								: "/admin/mcp-servers"
						}
						icon="fa-scroll"
						label="Add Prompt"
					/>
				</div>
				<div className="card">
					<PromptDiagram />
					<p>
						A <strong>prompt</strong> is a reusable instruction template stored
						on an MCP server — its content is prepended to a user's message as
						extra context for the agent. Add one to the built-in server to give
						every user quick access to guidance you'd otherwise repeat by hand.
					</p>
				</div>
			</div>

			<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
				<div
					className="flex-gap"
					style={{ justifyContent: "space-between", alignItems: "flex-start" }}
				>
					<WizardSectionHeading step={ADVANCED_STEPS[1]} index={1} />
					<StepAction
						complete={hasCustomServer}
						to="/admin/mcp-servers/new"
						icon="fa-server"
						label="Add Server"
					/>
				</div>
				<div className="card">
					<McpDiagram />
					<p>
						An <strong>MCP server</strong> plugs extra tools into the agent
						beyond the built-in ones — either a remote server reachable over
						HTTP, or a local subprocess TetherDust spawns and manages for you.
						Roles can grant access to specific MCP servers, so custom tools stay
						scoped to the users who need them.
					</p>
				</div>
			</div>
		</>
	);
}

const TAB_CONTENT: Record<Exclude<TabKey, "welcome">, () => ReactElement> = {
	foundations: FoundationsTab,
	roles: RoleManagementTab,
	analytics: AnalyticsTab,
	advanced: AdvancedTab,
};

export function GettingStartedPage() {
	const [tab, setTab] = useState<TabKey>("welcome");

	let content: ReactElement;
	if (tab === "welcome") {
		content = <WelcomeTab onGetStarted={() => setTab("foundations")} />;
	} else {
		const TabContent = TAB_CONTENT[tab];
		content = <TabContent />;
	}

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Getting Started</h1>
					<p>A quick-start guide for setting up and using TetherDust</p>
				</div>
			</div>

			<div className="tab-bar" style={{ marginBottom: "var(--lg)" }}>
				{TABS.map((t) => (
					<button
						key={t.key}
						type="button"
						className={`tab-item${tab === t.key ? " active" : ""}`}
						onClick={() => setTab(t.key)}
					>
						{t.label}
					</button>
				))}
			</div>

			{content}
		</div>
	);
}
