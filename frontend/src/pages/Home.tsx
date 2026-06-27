import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

// Index route: send the user to their first accessible section, mirroring the
// legacy `_default_redirect` logic.
export function HomeRedirect() {
  const { user } = useAuth();
  if (!user) {
    return <Navigate to="/login" replace />;
  }
  const p = user.permissions;
  const target = p.can_chat
    ? "/chat"
    : p.can_view_docs
      ? "/docs"
      : p.can_view_reports
        ? "/reports"
        : p.can_view_dashboards
          ? "/dashboards"
          : p.can_view_tethers
            ? "/tethers"
            : "/chat";
  return <Navigate to={target} replace />;
}
