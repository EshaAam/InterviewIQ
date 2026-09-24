"use client";

import { SessionProvider } from "@/components/session-provider";

/**
 * Everything under this group is behind a token. The user is resolved once
 * here and shared by context, so a page navigation does not re-ask the
 * backend who you are.
 */
export default function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <SessionProvider>{children}</SessionProvider>;
}
