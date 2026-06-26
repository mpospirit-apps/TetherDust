import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, useParams } from "react-router-dom";
import { getDashboard, getDashboards } from "../api/dashboards";
import { ChartCard } from "./ChartCard";

function DashboardContent({ id }: { id: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["dashboard", id],
    queryFn: () => getDashboard(id),
  });

  if (isLoading) {
    return (
      <div className="docs-loading">
        <i className="fa-solid fa-spinner fa-spin" />
      </div>
    );
  }
  if (isError || !data) {
    return <p className="text-sec">Failed to load this dashboard.</p>;
  }

  // Auto-refresh interval (minutes → ms) when enabled and valid; otherwise no polling.
  const intervalMinutes = Number(data.refresh_interval);
  const refreshIntervalMs =
    data.auto_refresh && Number.isFinite(intervalMinutes) && intervalMinutes > 0
      ? intervalMinutes * 60_000
      : undefined;

  return (
    <div className="dashboard-view">
      <div className="dashboard-view__header">
        <h1>{data.name}</h1>
        {data.description && <p>{data.description}</p>}
        {refreshIntervalMs && (
          <p className="text-sec">
            <i className="fa-solid fa-rotate" /> Auto-refreshes every{" "}
            {intervalMinutes >= 60
              ? `${intervalMinutes / 60} hour${intervalMinutes >= 120 ? "s" : ""}`
              : `${intervalMinutes} minutes`}
          </p>
        )}
      </div>
      {data.charts.length === 0 ? (
        <p className="text-sec">This dashboard has no charts.</p>
      ) : (
        <div className="dashboard-grid">
          {data.charts.map((chart) => (
            <ChartCard key={chart.id} chart={chart} refreshIntervalMs={refreshIntervalMs} />
          ))}
        </div>
      )}
    </div>
  );
}

export function DashboardsPage() {
  const { id } = useParams();
  const [search, setSearch] = useState("");
  const { data, isLoading } = useQuery({ queryKey: ["dashboards"], queryFn: getDashboards });

  const dashboards = (data?.dashboards ?? []).filter((d) =>
    d.name.toLowerCase().includes(search.trim().toLowerCase())
  );

  return (
    <div className="docs-layout">
      <aside className="docs-sidebar">
        <div className="docs-sidebar-header">
          <h3>Dashboards</h3>
        </div>
        <div className="history-search">
          <i className="fa-solid fa-magnifying-glass" />
          <input
            type="text"
            placeholder="Search dashboards…"
            autoComplete="off"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="docs-tree">
          {isLoading ? (
            <p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
              Loading…
            </p>
          ) : dashboards.length === 0 ? (
            <p className="text-sec" style={{ padding: "var(--md) var(--lg)" }}>
              No dashboards available.
            </p>
          ) : (
            dashboards.map((d) => (
              <NavLink
                key={d.id}
                to={`/dashboards/${d.id}`}
                className={({ isActive }) =>
                  isActive ? "docs-file-btn active" : "docs-file-btn"
                }
              >
                <i className="fa-solid fa-chart-pie" />
                <span>{d.name}</span>
              </NavLink>
            ))
          )}
        </div>
      </aside>

      <div className="docs-content-area">
        {id ? (
          <DashboardContent id={id} />
        ) : (
          <div className="docs-empty-state">
            <div className="empty-brand">
              Tether<span>Dust</span>
            </div>
            <p>Select a dashboard from the sidebar to view its charts.</p>
          </div>
        )}
      </div>
    </div>
  );
}
