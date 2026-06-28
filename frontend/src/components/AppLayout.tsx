import { useEffect } from "react";
import { Outlet } from "react-router-dom";
import { AuroraBackground } from "./AuroraBackground";
import { Navbar } from "./Navbar";

// Authenticated app chrome: aurora backdrop + navbar + routed content.
export function AppLayout() {
	useEffect(() => {
		document.body.classList.add("aurora-bg");
		return () => document.body.classList.remove("aurora-bg");
	}, []);

	return (
		<>
			<AuroraBackground />
			<Navbar />
			<main>
				<Outlet />
			</main>
		</>
	);
}
