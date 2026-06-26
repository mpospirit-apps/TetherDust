import { useQuery } from "@tanstack/react-query";
import { getAuditLog } from "../../api/admin";

export function AuditPage() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "audit"],
    queryFn: getAuditLog,
  });
  const logs = data?.results ?? [];

  return (
    <div>
      <div className="page-header">
        <div>
          <h1>Audit Log</h1>
          <p>Recent database queries run by agents (latest 200).</p>
        </div>
      </div>
      <div className="card">
        {isLoading ? (
          <p className="text-sec">Loading…</p>
        ) : isError ? (
          <p className="text-sec">Failed to load audit log.</p>
        ) : logs.length === 0 ? (
          <p className="text-sec">No queries logged yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>User</th>
                  <th>Database</th>
                  <th>Status</th>
                  <th>Rows</th>
                  <th>ms</th>
                  <th>Query</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td className="text-mono">{new Date(l.created_at).toLocaleString()}</td>
                    <td>{l.user ?? "—"}</td>
                    <td>{l.database ?? "—"}</td>
                    <td>
                      {l.success ? (
                        <span className="badge badge-success">OK</span>
                      ) : (
                        <span className="badge badge-error" title={l.error_message}>
                          ERROR
                        </span>
                      )}
                    </td>
                    <td>{l.row_count ?? "—"}</td>
                    <td>{l.execution_time_ms ?? "—"}</td>
                    <td className="text-mono truncate" title={l.query} style={{ maxWidth: 360 }}>
                      {l.query}
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
