// D3 chart rendering — ports the legacy static/js/charts/render.js. The stored
// `custom_d3_code` for each chart is executed via `new Function` (same as the
// server-rendered app); d3 is bundled and exposed on window so that code can use
// it. ⚠️ This is eval-of-stored-code: charts are authored by staff/the agent and
// the bundle is same-origin, but treat chart code as trusted input.

import * as d3 from "d3";

declare global {
  interface Window {
    d3: typeof d3;
  }
}

window.d3 = d3;

export interface ChartTheme {
  colors: string[];
  text: string;
  textSec: string;
  textMuted: string;
  border: string;
  surface: string;
  accent: string;
  mode: string;
}

export function readCssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function buildTheme(): ChartTheme {
  const palette = [
    readCssVar("--c-red"),
    readCssVar("--c-cyan"),
    readCssVar("--c-lime"),
    readCssVar("--c-orange"),
    readCssVar("--c-pink"),
  ].filter(Boolean);
  return {
    colors: palette,
    text: readCssVar("--text"),
    textSec: readCssVar("--text-sec"),
    textMuted: readCssVar("--text-muted"),
    border: readCssVar("--border"),
    surface: readCssVar("--surface"),
    accent: readCssVar("--c-red"),
    mode: document.documentElement.getAttribute("data-theme") || "light",
  };
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

// Some chart code is a function *body* (`const svg = d3.select(container)…`),
// other code (notably AI-generated) is a bare function *expression*
// (`(function(data, container, d3, theme){…})`) that, as a body, is defined and
// discarded — never called. Evaluate such code to its function so we can invoke it.
function asFactory(
  d3Code: string
): ((data: unknown, container: HTMLElement, d3: unknown, theme: ChartTheme) => void) | null {
  try {
    const value = new Function("return (" + d3Code + ");")();
    return typeof value === "function" ? value : null;
  } catch {
    return null;
  }
}

// Runs the chart code against a container. Returns an error message on failure,
// or null on success — the caller decides how to surface it.
export function runChartCode(
  container: HTMLElement,
  d3Code: string,
  data: unknown,
  theme: ChartTheme
): string | null {
  container.innerHTML = "";
  try {
    new Function("data", "container", "d3", "theme", d3Code)(data, container, window.d3, theme);
  } catch (e) {
    // Body execution failed — retry as a bare function expression.
    const fn = asFactory(d3Code);
    if (fn) {
      try {
        container.innerHTML = "";
        fn(data, container, window.d3, theme);
        return null;
      } catch (e2) {
        return errMsg(e2);
      }
    }
    return errMsg(e);
  }
  // Body ran without error but produced nothing — the code was likely a function
  // expression rather than a body; evaluate and invoke it.
  if (container.childElementCount === 0) {
    const fn = asFactory(d3Code);
    if (fn) {
      try {
        fn(data, container, window.d3, theme);
      } catch (e) {
        return errMsg(e);
      }
    }
  }
  return null;
}

export function renderChart(
  container: HTMLElement,
  d3Code: string,
  data: unknown,
  theme: ChartTheme
): void {
  const err = runChartCode(container, d3Code, data, theme);
  if (err) {
    container.innerHTML =
      '<div class="chart-card__error"><i class="fa-solid fa-triangle-exclamation"></i> Render error: ' +
      err +
      "</div>";
  }
}

export function timesince(iso: string | null | undefined): string {
  if (!iso) return "Not cached";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "Not cached";
  const diff = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diff < 60) return "just now";
  if (diff < 3600) return Math.floor(diff / 60) + " min ago";
  if (diff < 86400) return Math.floor(diff / 3600) + " hr ago";
  return Math.floor(diff / 86400) + " d ago";
}
