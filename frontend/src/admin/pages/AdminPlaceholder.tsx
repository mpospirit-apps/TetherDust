import { useLocation } from "react-router-dom";

// Fallback for admin sidebar sections not yet built into their feature vertical.
export function AdminPlaceholder() {
	const { pathname } = useLocation();
	const name = pathname.replace("/admin/", "").replace(/-/g, " ") || "section";
	return (
		<div>
			<div className="page-header">
				<div>
					<h1 style={{ textTransform: "capitalize" }}>{name}</h1>
					<p>This admin section is wired up in a later step.</p>
				</div>
			</div>
			<div className="card">
				<div className="empty-state">
					<div className="icon">
						<i className="fa-solid fa-screwdriver-wrench" />
					</div>
					<h3>Coming soon</h3>
					<p className="text-sec">
						This section lights up as its feature vertical lands.
					</p>
				</div>
			</div>
		</div>
	);
}
