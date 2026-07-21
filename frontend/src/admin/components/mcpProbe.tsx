import type { MCPProbeResult } from "../../api/mcp";

// Shared between the MCP Servers list (inline row test) and the Add/Edit MCP
// Server form (header Test button) so both surfaces stay in sync — styled
// like Database Connection's flash-success/flash-error test result.
export function ProbeReport({ result }: { result: MCPProbeResult }) {
	return (
		<div className={`flash ${result.ok ? "flash-success" : "flash-error"}`}>
			<p style={{ margin: 0, fontWeight: 600 }}>
				{result.ok ? "Connected ✓" : "Failed"}
			</p>
			{result.url && (
				<p className="text-sm" style={{ margin: "var(--xs) 0 0" }}>
					Probed <span className="text-mono">{result.url}</span>
					{result.transport ? ` (${result.transport})` : ""}
				</p>
			)}
			{result.error && (
				<p className="text-sm" style={{ margin: "var(--xs) 0 0" }}>
					{result.error}
				</p>
			)}
			{result.initialize && (
				<p className="text-sm" style={{ margin: "var(--xs) 0 0" }}>
					initialize: HTTP {result.initialize.status_code} in{" "}
					{result.initialize.elapsed_ms}ms
					{result.initialize.server_name
						? ` · ${result.initialize.server_name}`
						: ""}
					{result.initialize.server_version
						? ` v${result.initialize.server_version}`
						: ""}
				</p>
			)}
			{result.tools_list?.count != null && (
				<div style={{ marginTop: "var(--xs)" }}>
					<p className="text-sm" style={{ margin: 0 }}>
						tools/list: {result.tools_list.count} tool(s) in{" "}
						{result.tools_list.elapsed_ms}ms
					</p>
					<ul className="text-sm" style={{ margin: "var(--xs) 0 0" }}>
						{(result.tools_list.tools ?? []).map((t) => (
							<li key={t.name}>
								<strong>{t.name}</strong>
								{t.description ? ` — ${t.description}` : ""}
							</li>
						))}
					</ul>
				</div>
			)}
		</div>
	);
}
