"use client";

import { RequireRole } from "@/components/session-provider";

export default function RecruiterLayout({ children }: { children: React.ReactNode }) {
  return <RequireRole role="recruiter">{children}</RequireRole>;
}
