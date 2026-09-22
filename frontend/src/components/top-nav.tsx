"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { clearTokens, type User } from "@/lib/auth";
import { recallSession } from "@/lib/use-user";

/**
 * App chrome. The link set is driven by role, not by a prop, so a candidate
 * can never be shown a recruiter route that would 403 on arrival.
 */
export function TopNav({ user }: { user: User | null }) {
  const pathname = usePathname();
  const router = useRouter();

  const lastSession = recallSession();
  const links =
    user?.role === "recruiter"
      ? [
          { href: "/recruiter/sessions", label: "Sessions" },
          { href: "/recruiter/review", label: "Review queue" },
          { href: "/recruiter/costs", label: "Costs" },
        ]
      : [
          { href: "/interview", label: "Interview" },
          ...(lastSession
            ? [{ href: `/reports/${lastSession}`, label: "Report" }]
            : []),
        ];

  function signOut() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <header className="flex h-16 items-center justify-between border-b border-line bg-surface px-8">
      <div className="flex items-center gap-8">
        <Link href={user?.role === "recruiter" ? "/recruiter/sessions" : "/interview"}>
          <span className="flex items-center gap-2">
            <span className="size-[22px] rounded-full bg-accent" />
            <span className="font-semibold text-ink">InterviewIQ</span>
          </span>
        </Link>
        <nav className="flex items-center gap-6">
          {links.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`text-sm ${active ? "font-medium text-ink" : "text-ink-2 hover:text-ink"}`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      </div>

      <div className="flex items-center gap-3">
        {user && (
          <span className="rounded-full bg-accent-subtle px-2.5 py-1 text-[11px] font-medium text-accent">
            {user.role}
          </span>
        )}
        <button
          onClick={signOut}
          title={user?.email ?? "Sign out"}
          className="flex size-8 items-center justify-center rounded-full bg-canvas text-xs font-medium text-ink-2 hover:bg-line"
        >
          {user ? user.email.slice(0, 2).toUpperCase() : "—"}
        </button>
      </div>
    </header>
  );
}
