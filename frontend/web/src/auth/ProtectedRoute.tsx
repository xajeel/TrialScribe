import { Navigate, Outlet } from "react-router-dom";

import { SessionCheckPage } from "../pages/SessionCheckPage";
import { useAuth } from "./useAuth";

/** Gate for authenticated routes: wait, redirect, or render the child route. */
export function ProtectedRoute() {
  const { status } = useAuth();
  if (status === "loading") {
    return <SessionCheckPage />;
  }
  if (status === "anonymous") {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}
