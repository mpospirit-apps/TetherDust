import { Navigate, Route, Routes } from "react-router-dom";
import { AdminLayout } from "./admin/AdminLayout";
import { AdminDashboardDetailPage } from "./admin/pages/AdminDashboardDetailPage";
import { AdminDashboardFormPage } from "./admin/pages/AdminDashboardFormPage";
import { AdminDashboardsPage } from "./admin/pages/AdminDashboardsPage";
import { AdminHome } from "./admin/pages/AdminHome";
import { AdminPlaceholder } from "./admin/pages/AdminPlaceholder";
import { AdminTethersPage } from "./admin/pages/AdminTethersPage";
import { AgentFormPage } from "./admin/pages/AgentFormPage";
import { AgentsPage } from "./admin/pages/AgentsPage";
import { AuditLogDetailPage } from "./admin/pages/AuditLogDetailPage";
import { AuditPage } from "./admin/pages/AuditPage";
import { ChartFormPage } from "./admin/pages/ChartFormPage";
import { ChartGenLogDetailPage } from "./admin/pages/ChartGenLogDetailPage";
import { ChartGenLogsPage } from "./admin/pages/ChartGenLogsPage";
import { CodebaseFormPage } from "./admin/pages/CodebaseFormPage";
import { CodebasesPage } from "./admin/pages/CodebasesPage";
import { DashboardAddPage } from "./admin/pages/DashboardAddPage";
import { DashboardGeneratePage } from "./admin/pages/DashboardGeneratePage";
import { DatabaseFormPage } from "./admin/pages/DatabaseFormPage";
import { DatabasesPage } from "./admin/pages/DatabasesPage";
import { DocGeneratePage } from "./admin/pages/DocGeneratePage";
import { DocGenLogDetailPage } from "./admin/pages/DocGenLogDetailPage";
import { DocGenLogsPage } from "./admin/pages/DocGenLogsPage";
import { DocLibraryPage } from "./admin/pages/DocLibraryPage";
import { DocSourceAddPage } from "./admin/pages/DocSourceAddPage";
import { DocSourceFormPage } from "./admin/pages/DocSourceFormPage";
import { DocSourcesPage } from "./admin/pages/DocSourcesPage";
import { GettingStartedPage } from "./admin/pages/GettingStartedPage";
import { MCPServerDetailPage } from "./admin/pages/MCPServerDetailPage";
import { MCPServerFormPage } from "./admin/pages/MCPServerFormPage";
import { MCPServersPage } from "./admin/pages/MCPServersPage";
import { ReportFormPage } from "./admin/pages/ReportFormPage";
import { ReportRunDetailPage } from "./admin/pages/ReportRunDetailPage";
import { ReportRunsPage } from "./admin/pages/ReportRunsPage";
import { AdminReportsPage } from "./admin/pages/ReportsPage";
import { RoleFormPage } from "./admin/pages/RoleFormPage";
import { RolesPage } from "./admin/pages/RolesPage";
import { SessionDetailPage } from "./admin/pages/SessionDetailPage";
import { SessionsPage } from "./admin/pages/SessionsPage";
import { SettingsPage } from "./admin/pages/SettingsPage";
import { TetherDetailPage } from "./admin/pages/TetherDetailPage";
import { TetherFormPage } from "./admin/pages/TetherFormPage";
import { UserFormPage } from "./admin/pages/UserFormPage";
import { UsersPage } from "./admin/pages/UsersPage";
import { VersionPage } from "./admin/pages/VersionPage";
import { RequireStaff } from "./admin/RequireStaff";
import { RequireAuth } from "./auth/RequireAuth";
import { ChatPage } from "./chat/ChatPage";
import { AppLayout } from "./components/AppLayout";
import { DashboardsPage } from "./dashboards/DashboardsPage";
import { DocsPage } from "./docs/DocsPage";
import { HomeRedirect } from "./pages/Home";
import { LoginPage } from "./pages/LoginPage";
import { ReportsPage } from "./reports/ReportsPage";
import { TethersPage } from "./tethers/TethersPage";

export function App() {
	return (
		<Routes>
			<Route path="/login" element={<LoginPage />} />
			<Route
				element={
					<RequireAuth>
						<AppLayout />
					</RequireAuth>
				}
			>
				<Route index element={<HomeRedirect />} />
				<Route path="chat" element={<ChatPage />} />
				<Route path="docs" element={<DocsPage />} />
				<Route path="docs/:source/*" element={<DocsPage />} />
				<Route path="reports" element={<ReportsPage />} />
				<Route path="dashboards" element={<DashboardsPage />} />
				<Route path="dashboards/:id" element={<DashboardsPage />} />
				<Route path="tethers" element={<TethersPage />} />
				<Route path="tethers/:id" element={<TethersPage />} />
			</Route>
			<Route
				path="/admin"
				element={
					<RequireStaff>
						<AdminLayout />
					</RequireStaff>
				}
			>
				<Route index element={<AdminHome />} />
				<Route path="getting-started" element={<GettingStartedPage />} />
				<Route path="version" element={<VersionPage />} />
				<Route path="databases" element={<DatabasesPage />} />
				<Route path="databases/new" element={<DatabaseFormPage />} />
				<Route path="databases/:id" element={<DatabaseFormPage />} />
				<Route path="docsources" element={<DocSourcesPage />} />
				<Route path="docsources/add" element={<DocSourceAddPage />} />
				<Route path="docsources/register" element={<DocSourceFormPage />} />
				<Route path="docsources/generate" element={<DocGeneratePage />} />
				<Route path="docsources/library" element={<DocLibraryPage />} />
				<Route path="docsources/:id" element={<DocSourceFormPage />} />
				<Route path="docgen-logs" element={<DocGenLogsPage />} />
				<Route path="docgen-logs/:id" element={<DocGenLogDetailPage />} />
				<Route path="dashboards" element={<AdminDashboardsPage />} />
				<Route path="dashboards/add" element={<DashboardAddPage />} />
				<Route path="dashboards/new" element={<AdminDashboardFormPage />} />
				<Route path="dashboards/generate" element={<DashboardGeneratePage />} />
				<Route path="dashboards/:id" element={<AdminDashboardDetailPage />} />
				<Route
					path="dashboards/:id/edit"
					element={<AdminDashboardFormPage />}
				/>
				<Route
					path="dashboards/:dashId/charts/new"
					element={<ChartFormPage />}
				/>
				<Route
					path="dashboards/:dashId/charts/:chartId"
					element={<ChartFormPage />}
				/>
				<Route path="chartgen-logs" element={<ChartGenLogsPage />} />
				<Route path="chartgen-logs/:id" element={<ChartGenLogDetailPage />} />
				<Route path="reports" element={<AdminReportsPage />} />
				<Route path="reports/new" element={<ReportFormPage />} />
				<Route path="reports/:id" element={<ReportFormPage />} />
				<Route path="report-runs" element={<ReportRunsPage />} />
				<Route path="report-runs/:id" element={<ReportRunDetailPage />} />
				<Route path="codebases" element={<CodebasesPage />} />
				<Route path="codebases/new" element={<CodebaseFormPage />} />
				<Route path="codebases/:id" element={<CodebaseFormPage />} />
				<Route path="tethers" element={<AdminTethersPage />} />
				<Route path="tethers/new" element={<TetherFormPage />} />
				<Route path="tethers/:id" element={<TetherDetailPage />} />
				<Route path="tethers/:id/edit" element={<TetherFormPage />} />
				<Route path="settings" element={<SettingsPage />} />
				<Route path="roles" element={<RolesPage />} />
				<Route path="roles/new" element={<RoleFormPage />} />
				<Route path="roles/:id" element={<RoleFormPage />} />
				<Route path="users" element={<UsersPage />} />
				<Route path="users/new" element={<UserFormPage />} />
				<Route path="users/:id" element={<UserFormPage />} />
				<Route path="audit" element={<AuditPage />} />
				<Route path="audit/:id" element={<AuditLogDetailPage />} />
				<Route path="sessions" element={<SessionsPage />} />
				<Route path="sessions/:id" element={<SessionDetailPage />} />
				<Route path="agents" element={<AgentsPage />} />
				<Route path="agents/new" element={<AgentFormPage />} />
				<Route path="agents/:id" element={<AgentFormPage />} />
				<Route path="mcp-servers" element={<MCPServersPage />} />
				<Route path="mcp-servers/new" element={<MCPServerFormPage />} />
				<Route path="mcp-servers/:id" element={<MCPServerDetailPage />} />
				<Route path="mcp-servers/:id/edit" element={<MCPServerFormPage />} />
				<Route path="*" element={<AdminPlaceholder />} />
			</Route>
			<Route path="*" element={<Navigate to="/" replace />} />
		</Routes>
	);
}
