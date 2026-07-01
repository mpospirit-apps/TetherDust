import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiErrorDetail } from "../../api/client";
import { deleteMCPServer, listMCPServers, type MCPServer } from "../../api/mcp";

function serverKind(s: MCPServer): string {
	if (s.is_builtin) return "Built-in";
	if (s.is_local) return "Local (subprocess)";
	return "Remote (HTTP)";
}

export function MCPServersPage() {
	const queryClient = useQueryClient();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "mcp-servers"],
		queryFn: listMCPServers,
	});
	const remove = useMutation({
		mutationFn: deleteMCPServer,
		onSuccess: () =>
			queryClient.invalidateQueries({ queryKey: ["admin", "mcp-servers"] }),
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});

	function onDelete(s: MCPServer) {
		if (window.confirm(`Delete MCP server "${s.name}"?`)) {
			remove.mutate(s.id);
		}
	}

	const servers = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>MCP Servers</h1>
					<p>
						Register custom MCP servers (remote HTTP or local subprocess) for
						the agent.
					</p>
				</div>
				<Link to="/admin/mcp-servers/new" className="btn btn-primary">
					+ Add Server
				</Link>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load MCP servers.</p>
				) : servers.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-server" />
						</div>
						<h3>No MCP servers yet</h3>
						<p className="text-sec">
							Register a custom MCP server to extend the agent's tools.
						</p>
						<Link to="/admin/mcp-servers/new" className="btn btn-primary mt-md">
							+ Add Server
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Name</th>
									<th>Type</th>
									<th>Tools</th>
									<th>Status</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{servers.map((s) => (
									<tr key={s.id}>
										<td>
											<strong>{s.name}</strong>
											{s.description && (
												<div className="text-sec text-sm">{s.description}</div>
											)}
										</td>
										<td>
											<span className="type-badge">{serverKind(s)}</span>
										</td>
										<td className="text-mono">{s.tool_count}</td>
										<td>
											{s.is_active ? (
												<span className="badge badge-success">ACTIVE</span>
											) : (
												<span className="badge badge-muted">INACTIVE</span>
											)}
										</td>
										<td>
											<div className="flex-gap">
												<Link
													to={`/admin/mcp-servers/${s.id}`}
													className="btn btn-ghost btn-sm"
												>
													<i className="fa-solid fa-eye" /> View
												</Link>
												{!s.is_builtin && (
													<>
														<Link
															to={`/admin/mcp-servers/${s.id}/edit`}
															className="btn btn-ghost btn-sm"
														>
															<i className="fa-solid fa-pen" /> Edit
														</Link>
														<button
															type="button"
															className="btn btn-ghost btn-sm"
															style={{ color: "var(--danger)" }}
															onClick={() => onDelete(s)}
														>
															<i className="fa-solid fa-trash" /> Delete
														</button>
													</>
												)}
											</div>
										</td>
									</tr>
								))}
							</tbody>
						</table>
					</div>
				)}
			</div>
		</div>
	);
}
