import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import * as api from "../lib/api";
import type { User } from "../lib/api";

type AuthState =
  | { status: "loading" }
  | { status: "anonymous" }
  | { status: "authenticated"; user: User };

interface AuthContextValue {
  state: AuthState;
  signIn: (name: string, phone: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });

  const forceSignedOut = useCallback(() => {
    api.clearToken();
    setState({ status: "anonymous" });
  }, []);

  // Any 401 from the API (expired or revoked session) sends the visitor back
  // to the entry screen.
  useEffect(() => {
    api.setUnauthorizedHandler(forceSignedOut);
    return () => api.setUnauthorizedHandler(null);
  }, [forceSignedOut]);

  // Restore a previous session on page load.
  useEffect(() => {
    if (!api.getToken()) {
      setState({ status: "anonymous" });
      return;
    }
    let cancelled = false;
    api
      .fetchMe()
      .then(({ user }) => !cancelled && setState({ status: "authenticated", user }))
      .catch((err: unknown) => {
        if (cancelled) return;
        // A dead network shouldn't throw away a valid session.
        if (err instanceof api.ApiError && err.status === 0) {
          setState({ status: "anonymous" });
        } else {
          forceSignedOut();
        }
      });
    return () => {
      cancelled = true;
    };
  }, [forceSignedOut]);

  const signIn = useCallback(async (name: string, phone: string) => {
    const { token, user } = await api.register(name, phone);
    api.setToken(token);
    setState({ status: "authenticated", user });
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* the local session is cleared either way */
    }
    forceSignedOut();
  }, [forceSignedOut]);

  const value = useMemo(() => ({ state, signIn, signOut }), [state, signIn, signOut]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
