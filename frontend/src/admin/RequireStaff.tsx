import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// Guard for the admin console: authenticated AND staff.
export function RequireStaff({ children }: { children: ReactNode }) {
	const { user, loading } = useAuth();
	if (loading) {
		return <div className="app-loading">Loading…</div>;
	}
	if (!user) {
		return <Navigate to="/login" replace />;
	}
	if (!user.is_staff) {
		return <Navigate to="/" replace />;
	}
	return <>{children}</>;
}
