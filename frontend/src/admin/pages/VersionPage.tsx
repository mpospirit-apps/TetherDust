import { useQuery } from "@tanstack/react-query";
import { getVersionInfo } from "../../api/admin";
import { DocMarkdown } from "../../docs/DocMarkdown";

const GITHUB_URL = "https://github.com/mpospirit-apps/TetherDust";

export function VersionPage() {
	const { data, isLoading, isError } = useQuery({
		queryKey: ["admin", "version"],
		queryFn: getVersionInfo,
	});

	return (
		<div className="version-page">
			<div className="page-header">
				<div>
					<h1>Version</h1>
					<p>
						Running release, update status, and upgrade notes for TetherDust
					</p>
				</div>
			</div>

			{isLoading ? (
				<div className="card">
					<p className="text-sec">Loading…</p>
				</div>
			) : isError || !data ? (
				<div className="card">
					<p className="text-sec">Failed to load version information.</p>
				</div>
			) : (
				<>
					<div className="card" style={{ marginBottom: "var(--lg)" }}>
						<dl
							style={{
								display: "grid",
								gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
								gap: "var(--md)",
								margin: 0,
							}}
						>
							<div>
								<dt className="text-sec text-sm">Current version</dt>
								<dd style={{ fontSize: "var(--text-lg)", fontWeight: 700 }}>
									{data.current_version}
								</dd>
							</div>
							<div>
								<dt className="text-sec text-sm">Latest release</dt>
								<dd style={{ fontSize: "var(--text-lg)", fontWeight: 700 }}>
									{data.latest_version || <span className="text-sec">—</span>}
								</dd>
							</div>
							<div>
								<dt className="text-sec text-sm">Status</dt>
								<dd>
									{data.update_available ? (
										<span className="badge badge-orange">Update available</span>
									) : data.latest_version ? (
										<span className="badge badge-success">Up to date</span>
									) : (
										<span className="badge badge-muted">Not checked</span>
									)}
								</dd>
							</div>
						</dl>

						{data.update_available && data.latest_release_url && (
							<div style={{ marginTop: "var(--md)" }}>
								<a
									href={data.latest_release_url}
									target="_blank"
									rel="noopener noreferrer"
									className="btn btn-primary"
								>
									<i className="fa-solid fa-arrow-up-right-from-square" /> View
									release {data.latest_version}
								</a>
								<p
									className="text-sec text-sm"
									style={{ margin: "var(--sm) 0 0" }}
								>
									Follow the upgrade notes for this version below before
									deploying.
								</p>
							</div>
						)}

						{data.latest_checked_at && (
							<p
								className="text-sec text-sm"
								style={{ margin: "var(--md) 0 0" }}
							>
								Last checked: {data.latest_checked_at}
							</p>
						)}
					</div>

					<p className="text-sec text-sm" style={{ margin: "0 0 var(--lg)" }}>
						Visit the{" "}
						<a href={GITHUB_URL} target="_blank" rel="noopener noreferrer">
							GitHub repository
						</a>{" "}
						to request features, report bugs, or view the roadmap.
					</p>

					<h3 style={{ margin: "0 0 var(--sm)" }}>Release notes</h3>
					{data.changelog_entries.length > 0 ? (
						data.changelog_entries.map((entry) => (
							<div
								key={entry.version}
								className="card"
								style={{ marginBottom: "var(--md)" }}
							>
								<div
									className="flex-gap"
									style={{ alignItems: "center", marginBottom: "var(--sm)" }}
								>
									<h2 style={{ margin: 0 }}>{entry.version}</h2>
									{entry.is_current && (
										<span className="badge badge-info">Current</span>
									)}
								</div>
								<DocMarkdown
									content={entry.raw}
									sources={[]}
									currentSource=""
								/>
							</div>
						))
					) : (
						<div className="card">
							<p className="text-sec">
								No release notes found in the <code>changelog/</code> directory.
							</p>
						</div>
					)}
				</>
			)}
		</div>
	);
}
