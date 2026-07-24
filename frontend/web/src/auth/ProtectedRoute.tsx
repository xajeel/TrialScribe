import { Navigate, Outlet } from "react-router-dom";

import { LoadingState } from "../components/AsyncState";
import { useAuth } from "./useAuth";

/** Gate for authenticated routes: wait, redirect, or render the child route. */
export function ProtectedRoute() {
  const { status } = useAuth();
  if (status === "loading") {
    return <LoadingState label="Restoring session…" />;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
