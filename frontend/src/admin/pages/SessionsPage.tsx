import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getSessions } from "../../api/admin";

export function SessionsPage() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "sessions"],
		queryFn: getSessions,
	});
	const sessions = data?.results ?? [];

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Chat Sessions</h1>
					<p>Recent chat sessions (latest 200).</p>
				</div>
			</div>
			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError ? (
					<p className="text-sec">Failed to load sessions.</p>
				) : sessions.length === 0 ? (
					<p className="text-sec">No sessions yet.</p>
				) : (
					<div className="table-wrap">
						<table>
							<thead>
								<tr>
									<th>Title</th>
									<th>User</th>
									<th>Messages</th>
									<th>Updated</th>
									<th />
								</tr>
							</thead>
							<tbody>
								{sessions.map((s) => (
									<tr key={s.id}>
										<td>
											<strong>{s.title || "(untitled)"}</strong>
											<div className="text-sec text-mono">{s.id}</div>
										</td>
										<td>{s.user ?? "—"}</td>
										<td>{s.message_count}</td>
										<td className="text-mono">
											{new Date(s.updated_at).toLocaleString()}
										</td>
										<td>
											<Link
												to={`/admin/sessions/${s.id}`}
												className="btn btn-ghost btn-sm"
											>
												<i className="fa-solid fa-eye" /> View
											</Link>
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
