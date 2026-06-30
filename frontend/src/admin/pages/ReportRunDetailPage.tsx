import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import { getExecution } from "../../api/reports";
import { ReportResultTable } from "../../reports/ReportResultTable";

export function ReportRunDetailPage() {
	const { id } = useParams();
	const { data, isLoading, isError } = useQuery({
		queryKey: ["execution", id],
		queryFn: () => getExecution(id as string),
		enabled: Boolean(id),
	});

	return (
		<div>
			<div className="page-header">
				<div>
					<h1>Report Run</h1>
					<p>{data ? data.report.name : "Execution results"}</p>
				</div>
				<Link to="/admin/report-runs" className="btn btn-ghost">
					Back
				</Link>
			</div>

			<div className="card">
				{isLoading ? (
					<p className="text-sec">Loading…</p>
				) : isError || !data ? (
					<p className="text-sec">Failed to load execution.</p>
				) : (
					<ReportResultTable
						report={data.report}
						execution={data.execution}
						emailEnabled={data.email_enabled}
					/>
				)}
			</div>
		</div>
	);
}
