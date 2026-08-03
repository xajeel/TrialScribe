import {
  createContext,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  acceptOrganizationInvitation,
  extractInvitationToken,
} from "../api/invitations";
import { ApiError } from "../api/client";
import {
  createOrganization,
  listOrganizations,
} from "../api/organizations";
import type { Organization } from "../api/types";
import { useAuth } from "../auth/useAuth";

export type OrganizationStatus = "idle" | "loading" | "ready" | "error";
export type OrganizationAction = "idle" | "creating" | "joining";

export interface OrganizationFeedback {
  kind: "success" | "error";
  message: string;
}

const STORAGE_KEY = "trialscribe.activeOrganization";
const CREATE_ERROR = "Could not create the organization. Please try again.";
const JOIN_ERROR =
  "Could not join the organization. Check the invitation and try again.";
const INVALID_INVITATION =
  "This invitation is invalid or has expired. Ask the sender for a new link.";

export interface OrganizationContextValue {
  status: OrganizationStatus;
  organizations: Organization[];
  activeId: string | null;
  action: OrganizationAction;
  feedback: OrganizationFeedback | null;
  select: (id: string) => void;
  reload: () => void;
  create: (name: string) => Promise<boolean>;
  join: (invitation: string) => Promise<boolean>;
  dismissFeedback: () => void;
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
  const [action, setAction] = useState<OrganizationAction>("idle");
  const [feedback, setFeedback] = useState<OrganizationFeedback | null>(null);
  const loadGeneration = useRef(0);
  const sessionGeneration = useRef(0);
  const actionInFlight = useRef(false);

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setStatus("loading");
    try {
      const items = await listOrganizations(authorizedFetch);
      if (generation !== loadGeneration.current) {
        return;
      }
      setOrganizations(items);
      const active = pickActive(items);
      setActiveId(active);
      if (active !== null) {
        localStorage.setItem(STORAGE_KEY, active);
      }
      setStatus("ready");
    } catch {
      if (generation === loadGeneration.current) {
        setStatus("error");
      }
    }
  }, [authorizedFetch]);

  useEffect(() => {
    sessionGeneration.current += 1;
    actionInFlight.current = false;
    setAction("idle");
    setFeedback(null);
    if (authStatus !== "authenticated") {
      loadGeneration.current += 1;
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

  const create = useCallback(
    async (name: string): Promise<boolean> => {
      const normalized = name.trim();
      if (
        normalized === "" ||
        normalized.length > 120 ||
        actionInFlight.current
      ) {
        if (normalized === "" || normalized.length > 120) {
          setFeedback({
            kind: "error",
            message: "Enter an organization name from 1 to 120 characters.",
          });
        }
        return false;
      }
      actionInFlight.current = true;
      const session = sessionGeneration.current;
      setAction("creating");
      setFeedback(null);
      try {
        const created = await createOrganization(authorizedFetch, normalized);
        if (session !== sessionGeneration.current) {
          return false;
        }
        setOrganizations((current) => [
          ...current.filter((item) => item.id !== created.id),
          created,
        ]);
        setActiveId(created.id);
        localStorage.setItem(STORAGE_KEY, created.id);
        setStatus("ready");
        setFeedback({
          kind: "success",
          message: `${created.name} created. Opening your workspace…`,
        });
        return true;
      } catch {
        if (session === sessionGeneration.current) {
          setFeedback({ kind: "error", message: CREATE_ERROR });
        }
        return false;
      } finally {
        if (session === sessionGeneration.current) {
          actionInFlight.current = false;
          setAction("idle");
        }
      }
    },
    [authorizedFetch],
  );

  const join = useCallback(
    async (invitation: string): Promise<boolean> => {
      const token = extractInvitationToken(invitation);
      if (token === null || actionInFlight.current) {
        if (token === null) {
          setFeedback({
            kind: "error",
            message: "Enter a valid invitation link or token.",
          });
        }
        return false;
      }
      actionInFlight.current = true;
      const session = sessionGeneration.current;
      setAction("joining");
      setFeedback(null);
      try {
        const membership = await acceptOrganizationInvitation(
          authorizedFetch,
          token,
        );
        const items = await listOrganizations(authorizedFetch);
        if (session !== sessionGeneration.current) {
          return false;
        }
        const joined = items.find(
          (item) => item.id === membership.organization_id,
        );
        if (joined === undefined) {
          throw new Error("Accepted organization was not returned");
        }
        setOrganizations(items);
        setActiveId(joined.id);
        localStorage.setItem(STORAGE_KEY, joined.id);
        setStatus("ready");
        setFeedback({
          kind: "success",
          message: `You joined ${joined.name}. Opening your workspace…`,
        });
        return true;
      } catch (error) {
        if (session === sessionGeneration.current) {
          setFeedback({
            kind: "error",
            message:
              error instanceof ApiError && error.status === 422
                ? INVALID_INVITATION
                : JOIN_ERROR,
          });
        }
        return false;
      } finally {
        if (session === sessionGeneration.current) {
          actionInFlight.current = false;
          setAction("idle");
        }
      }
    },
    [authorizedFetch],
  );

  const dismissFeedback = useCallback(() => {
    setFeedback(null);
  }, []);

  return (
    <OrganizationContext.Provider
      value={{
        status,
        organizations,
        activeId,
        action,
        feedback,
        select,
        reload,
        create,
        join,
        dismissFeedback,
      }}
    >
      {children}
    </OrganizationContext.Provider>
  );
}
