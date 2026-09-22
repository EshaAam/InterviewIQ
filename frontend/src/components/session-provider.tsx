"use client";

import { createContext, useContext, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useUser } from "@/lib/use-user";
import { type User, type UserRole } from "@/lib/auth";
import { TopNav } from "./top-nav";

const SignedInUser = createContext<User | null>(null);

/** The signed-in user. Only valid inside the authenticated layout. */
export function useSignedInUser(): User {
  const user = useContext(SignedInUser);
  if (!user) {
    throw new Error("useSignedInUser must be used inside the authenticated layout");
  }
  return user;
}

/**
 * Resolves the user once for the whole authenticated tree, renders the nav,
 * and refuses to render a page the user's role has no business seeing —
 * the backend would 403 anyway, this just fails earlier and more kindly.
 */
export function SessionProvider({
  children,
  requireRole,
}: {
  children: ReactNode;
  requireRole?: UserRole;
}) {
  const { user, loading } = useUser();
  const router = useRouter();

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-ink-3">
        Loading…
      </div>
    );
  }

  if (!user) return null; // useUser has already redirected to /login

  if (requireRole && user.role !== requireRole) {
    return (
      <>
        <TopNav user={user} />
        <div className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-3 text-center">
          <p className="text-sm text-ink">This area is for {requireRole} accounts.</p>
          <button
            onClick={() => router.replace("/interview")}
            className="text-sm font-medium text-accent"
          >
            Go to your interview
          </button>
        </div>
      </>
    );
  }

  return (
    <SignedInUser.Provider value={user}>
      <TopNav user={user} />
      {children}
    </SignedInUser.Provider>
  );
}

/**
 * Role gate for a subtree that is already inside the authenticated layout —
 * reads the user from context rather than re-fetching /auth/me.
 */
export function RequireRole({
  role,
  children,
}: {
  role: UserRole;
  children: ReactNode;
}) {
  const user = useSignedInUser();
  if (user.role !== role) {
    return (
      <div className="mx-auto flex max-w-md flex-1 flex-col items-center justify-center gap-2 py-24 text-center">
        <p className="text-sm text-ink">This area is for {role} accounts.</p>
        <p className="text-xs text-ink-3">
          You are signed in as {user.email} ({user.role}).
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
