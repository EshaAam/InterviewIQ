"use client";

import { createContext, useContext, type ReactNode } from "react";
import Link from "next/link";
import { ShieldAlert } from "lucide-react";
import { homeFor, useUser } from "@/lib/use-user";
import { type User, type UserRole } from "@/lib/auth";
import { TopNav } from "./top-nav";
import { buttonClass, EmptyState, Shell, Spinner } from "./ui";

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
 * Resolves the user once for the whole authenticated tree and renders the
 * nav. Role gating is not done here — that is `RequireRole`'s one job.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const { user, loading } = useUser();

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner />
      </div>
    );
  }

  if (!user) return null; // useUser has already redirected to /login

  return (
    <SignedInUser.Provider value={user}>
      <TopNav user={user} />
      {children}
    </SignedInUser.Provider>
  );
}

/**
 * Role gate for a subtree that is already inside the authenticated layout —
 * reads the user from context rather than re-fetching /auth/me. The backend
 * would 403 anyway; this just fails earlier and more kindly.
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
      <Shell width="narrow">
        <EmptyState
          icon={<ShieldAlert aria-hidden="true" className="size-6" />}
          title={`This area is for ${role} accounts`}
          action={
            <Link href={homeFor(user)} className={buttonClass("secondary", "sm")}>
              Go to your home page
            </Link>
          }
        >
          You are signed in as {user.email} ({user.role}).
        </EmptyState>
      </Shell>
    );
  }
  return <>{children}</>;
}
