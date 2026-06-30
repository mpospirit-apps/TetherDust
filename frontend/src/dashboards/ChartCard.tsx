import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import {
	type ChartData,
	type ChartView,
	getChartData,
} from "../api/dashboards";
import { buildTheme, renderChart, timesince } from "../charts/render";
import { useTheme } from "../hooks/useTheme";

export function ChartCard({
	chart,
	refreshIntervalMs,
}: {
	chart: ChartView;
	refreshIntervalMs?: number;
}) {
	const { theme } = useTheme();
	const queryClient = useQueryClient();
	const ref = useRef<HTMLDivElement>(null);

	const queryKey = ["chart-data", chart.id];
	const query = useQuery({ queryKey, queryFn: () => getChartData(chart.id) });
	const refresh = useMutation({
		mutationFn: () => getChartData(chart.id, true),
		onSuccess: (data: ChartData) => queryClient.setQueryData(queryKey, data),
	});

	// Dashboard auto-refresh: poll on the dashboard's interval, forcing a real
	// re-run (the manual-refresh path, `?refresh=1`) rather than re-serving the
	// server cache. The initial paint still uses cached data for speed. A ref
	// keeps the interval stable while always seeing the latest mutation state, so
	// we never stack a refresh on top of one still in flight.
	const refreshRef = useRef(refresh);
	refreshRef.current = refresh;
	useEffect(() => {
		if (!refreshIntervalMs) return;
		const handle = setInterval(() => {
			if (!refreshRef.current.isPending) refreshRef.current.mutate();
		}, refreshIntervalMs);
		return () => clearInterval(handle);
	}, [refreshIntervalMs]);

	const data = query.data;

	// The container is owned imperatively (D3 / innerHTML) — never give it React
	// children, and drive every state (loading / error / render) from here so the
	// two don't fight over the DOM.
	useEffect(() => {
		const el = ref.current;
		if (!el) return;
		if (query.isLoading) {
			el.innerHTML =
				'<div class="chart-card__loading"><i class="fa-solid fa-spinner fa-spin"></i> Loading…</div>';
			return;
		}
		if (query.isError) {
			el.innerHTML =
				'<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> Failed to load data</div>';
			return;
		}
		if (!data) return;
		if (data.error) {
			el.innerHTML =
				'<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> ' +
				data.error +
				"</div>";
			return;
		}
		renderChart(el, chart.custom_d3_code, data.data, buildTheme(theme));
	}, [query.isLoading, query.isError, data, theme, chart.custom_d3_code]);

	const refreshedAt = data?.refreshed_at ?? chart.last_refreshed_at;

	return (
		<div className="chart-card" style={{ gridColumn: `span ${chart.width}` }}>
			<div className="chart-card__header">
				<h4>{chart.title}</h4>
				<div className="chart-card__meta">
					<span className="chart-card__refresh-info">
						<i className="fa-regular fa-clock" /> {timesince(refreshedAt)}
					</span>
					<button
						type="button"
						className="chart-card__refresh-btn"
						title="Refresh data"
						disabled={refresh.isPending}
						onClick={() => refresh.mutate()}
					>
						<i
							className={`fa-solid fa-rotate${refresh.isPending ? " spinning" : ""}`}
						/>
					</button>
				</div>
			</div>
			<div className="chart-card__body">
				<div
					className="chart-container"
					style={{ height: `${chart.height}px` }}
					ref={ref}
				/>
			</div>
		</div>
	);
}
