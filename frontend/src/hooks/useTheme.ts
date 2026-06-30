import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark";

function currentTheme(): Theme {
	return document.documentElement.getAttribute("data-theme") === "dark"
		? "dark"
		: "light";
}

// Light/dark theme, mirroring the legacy shell: persisted under `td-theme` and
// applied as `data-theme` on <html> (the inline script in index.html sets it
// before paint; this keeps it in sync with React state).
export function useTheme() {
	const [theme, setTheme] = useState<Theme>(currentTheme);

	useEffect(() => {
		document.documentElement.setAttribute("data-theme", theme);
		localStorage.setItem("td-theme", theme);
	}, [theme]);

	const toggle = useCallback(() => {
		setTheme((t) => (t === "dark" ? "light" : "dark"));
	}, []);

	return { theme, toggle };
}
