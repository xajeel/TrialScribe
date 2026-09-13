import {
  createContext,
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { fetchMe, login, logout, refresh } from "../api/auth";
import { ApiError, apiFetch, tokenStore, type RequestOptions } from "../api/client";
import type { Account } from "../api/types";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export type AuthorizedFetch = <T>(
  path: string,
  opts?: RequestOptions,
) => Promise<T>;

export interface AuthContextValue {
  status: AuthStatus;
  account: Account | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  authorizedFetch: AuthorizedFetch;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [account, setAccount] = useState<Account | null>(null);
  const bootstrapped = useRef(false);
  const authGeneration = useRef(0);

  const becomeAnonymous = useCallback(() => {
    tokenStore.clear();
    setAccount(null);
    setStatus("anonymous");
  }, []);

  const becomeAuthenticated = useCallback((next: Account) => {
    setAccount(next);
    setStatus("authenticated");
  }, []);

  useEffect(() => {
    if (bootstrapped.current) {
      return;
    }
    bootstrapped.current = true;
    const generation = authGeneration.current;
    void (async () => {
      try {
        const tokens = await refresh();
        if (generation !== authGeneration.current) {
          return;
        }
        tokenStore.set(tokens.access_token);
        const nextAccount = await fetchMe();
        if (generation === authGeneration.current) {
          becomeAuthenticated(nextAccount);
        }
      } catch {
        if (generation === authGeneration.current) {
          becomeAnonymous();
        }
      }
    })();
  }, [becomeAnonymous, becomeAuthenticated]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      const generation = ++authGeneration.current;
      try {
        const tokens = await login(email, password);
        tokenStore.set(tokens.access_token);
        const nextAccount = await fetchMe();
        if (generation === authGeneration.current) {
          becomeAuthenticated(nextAccount);
        }
      } catch (error) {
        if (generation === authGeneration.current) {
          becomeAnonymous();
        }
        throw error;
      }
    },
    [becomeAnonymous, becomeAuthenticated],
  );

  const signOut = useCallback(async () => {
    const generation = ++authGeneration.current;
    try {
      await logout();
    } catch {
      // Best-effort revoke; clear the client session regardless.
    }
    if (generation === authGeneration.current) {
      becomeAnonymous();
    }
  }, [becomeAnonymous]);

  const authorizedFetch = useCallback<AuthorizedFetch>(
    async (path, opts) => {
      try {
        return await apiFetch(path, { ...opts, auth: true });
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) {
          throw error;
        }
        let tokens;
        try {
          tokens = await refresh();
        } catch (refreshError) {
          becomeAnonymous();
          throw refreshError;
        }
        tokenStore.set(tokens.access_token);
        return await apiFetch(path, { ...opts, auth: true });
      }
    },
    [becomeAnonymous],
  );

  return (
    <AuthContext.Provider
      value={{ status, account, signIn, signOut, authorizedFetch }}
    >
      {children}
    </AuthContext.Provider>
  );
}
