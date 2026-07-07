import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
	type Agent,
	activateAgent,
	deleteAgent,
	listAgents,
} from "../../api/admin";
import { apiErrorDetail } from "../../api/client";

export function AgentsPage() {
	const queryClient = useQueryClient();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "agents"],
		queryFn: listAgents,
	});
	const invalidate = () =>
		queryClient.invalidateQueries({ queryKey: ["admin", "agents"] });
	const activate = useMutation({
		mutationFn: activateAgent,
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Activate failed.")),
	});
	const remove = useMutation({
		mutationFn: deleteAgent,
		onSuccess: invalidate,
		onError: (err) => window.alert(apiErrorDetail(err, "Delete failed.")),
	});

	function onDelete(a: Agent) {
		if (window.confirm(`Delete agent "${a.name}"?`)) {
			remove.mutate(a.id);
		}
	}

	const agents = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Agents</h1>
					<p>
						Configure and activate the AI agent. Only one is active at a time.
					</p>
				</div>
				<Link to="/admin/agents/new" className="btn btn-primary">
					+ Add Agent
				</Link>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load agents.</p>
				) : agents.length === 0 ? (
					<div className="empty-state">
						<div className="icon">
							<i className="fa-solid fa-robot" />
						</div>
						<h3>No agents yet</h3>
						<p className="text-sec">
							Add an agent and activate it to start chatting.
						</p>
						<Link to="/admin/agents/new" className="btn btn-primary mt-md">
							+ Add Agent
						</Link>
					</div>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Name</th>
									<th>Type</th>
									<th>Credential</th>
									<th>Active</th>
									<th>Actions</th>
								</tr>
							</thead>
							<tbody>
								{agents.map((a) => (
									<tr key={a.id}>
										<td>
											<strong>{a.name}</strong>
										</td>
										<td>
											<span className="type-badge">{a.agent_type_display}</span>
										</td>
										<td>
											{a.has_api_key || a.has_auth_token ? (
												<span className="badge badge-success">Set</span>
											) : (
												<span className="badge badge-muted">None</span>
											)}
										</td>
										<td>
											{a.is_active ? (
												<span className="badge badge-success">ACTIVE</span>
											) : (
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													disabled={activate.isPending}
													onClick={() => activate.mutate(a.id)}
												>
													<i className="fa-solid fa-toggle-on" /> Activate
												</button>
											)}
										</td>
										<td>
											<div className="flex-gap">
												<Link
													to={`/admin/agents/${a.id}`}
													className="btn btn-ghost btn-sm"
												>
													<i className="fa-solid fa-pen" /> Edit
												</Link>
												<button
													type="button"
													className="btn btn-ghost btn-sm"
													style={{ color: "var(--danger)" }}
													disabled={a.is_active}
													title={
														a.is_active ? "Switch agents before deleting" : ""
													}
													onClick={() => onDelete(a)}
												>
													<i className="fa-solid fa-trash" /> Delete
												</button>
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
