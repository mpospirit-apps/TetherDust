import { useCallback, useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

function currentTheme(): Theme {
	return document.documentElement.getAttribute("data-theme") === "dark"
		? "dark"
		: "light";
}

// Every useTheme() call site needs to see the same value and re-render when
// any of them changes it — a plain per-component useState can't do that (each
// instance would only update on its own toggle() call), so the theme lives
// here as external state and every subscriber is notified on change.
const listeners = new Set<() => void>();

function applyTheme(theme: Theme) {
	document.documentElement.setAttribute("data-theme", theme);
	localStorage.setItem("td-theme", theme);
	for (const listener of listeners) listener();
}

function subscribe(listener: () => void) {
	listeners.add(listener);
	return () => listeners.delete(listener);
}

// Light/dark theme, mirroring the legacy shell: persisted under `td-theme` and
// applied as `data-theme` on <html> (the inline script in index.html sets it
// before paint; this keeps it in sync with React state).
export function useTheme() {
	const theme = useSyncExternalStore(
		subscribe,
		currentTheme,
		(): Theme => "light",
	);

	const toggle = useCallback(() => {
		applyTheme(currentTheme() === "dark" ? "light" : "dark");
	}, []);

	return { theme, toggle };
}
