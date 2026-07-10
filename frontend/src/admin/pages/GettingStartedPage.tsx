import { useQuery } from "@tanstack/react-query";
import { type ReactElement, useState } from "react";
import { Link } from "react-router-dom";
import {
	listAgents,
	listDatabases,
	listRoles,
	listUsers,
} from "../../api/admin";
import { listDashboards } from "../../api/dashboards";
import { listDocSources } from "../../api/docs";
import { listMCPServers } from "../../api/mcp";
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

	return (
		<div className="wizard-section" style={{ marginBottom: "var(--xl)" }}>
			<div
				className="flex-gap"
				style={{ justifyContent: "space-between", alignItems: "flex-start" }}
			>
				<WizardSectionHeading step={ADVANCED_STEPS[0]} index={0} />
				<StepAction
					complete={hasCustomServer}
					to="/admin/mcp-servers/new"
					icon="fa-server"
					label="Add Server"
				/>
			</div>
			<div className="card">
				<p>
					An <strong>MCP server</strong> plugs extra tools into the agent beyond
					the built-in ones — either a remote server reachable over HTTP, or a
					local subprocess TetherDust spawns and manages for you. Roles can
					grant access to specific MCP servers, so custom tools stay scoped to
					the users who need them.
				</p>
			</div>
		</div>
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
