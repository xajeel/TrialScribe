import {
  createContext,
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { listOrganizations } from "../api/organizations";
import type { Organization } from "../api/types";
import { useAuth } from "../auth/useAuth";

export type OrganizationStatus = "idle" | "loading" | "ready" | "error";

const STORAGE_KEY = "trialscribe.activeOrganization";

export interface OrganizationContextValue {
  status: OrganizationStatus;
  organizations: Organization[];
  activeId: string | null;
  select: (id: string) => void;
  reload: () => void;
}

export const OrganizationContext =
  createContext<OrganizationContextValue | null>(null);

function pickActive(organizations: Organization[]): string | null {
  const stored = localStorage.getItem(STORAGE_KEY);
  const match = organizations.find((item) => item.id === stored);
  return match?.id ?? organizations[0]?.id ?? null;
}

export function OrganizationProvider({ children }: { children: ReactNode }) {
  const { status: authStatus, authorizedFetch } = useAuth();
  const [status, setStatus] = useState<OrganizationStatus>("idle");
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const items = await listOrganizations(authorizedFetch);
      setOrganizations(items);
      const active = pickActive(items);
      setActiveId(active);
      if (active !== null) {
        localStorage.setItem(STORAGE_KEY, active);
      }
      setStatus("ready");
    } catch {
      setStatus("error");
    }
  }, [authorizedFetch]);

  useEffect(() => {
    if (authStatus !== "authenticated") {
      setOrganizations([]);
      setActiveId(null);
      setStatus("idle");
      return;
    }
    void load();
  }, [authStatus, load]);

  const select = useCallback((id: string) => {
    setActiveId(id);
    localStorage.setItem(STORAGE_KEY, id);
  }, []);

  const reload = useCallback(() => {
    void load();
  }, [load]);

  return (
    <OrganizationContext.Provider
      value={{ status, organizations, activeId, select, reload }}
    >
      {children}
    </OrganizationContext.Provider>
  );
}
