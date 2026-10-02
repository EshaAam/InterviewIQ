"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { motion } from "motion/react";
import { clearTokens, type User } from "@/lib/auth";
import { homeFor } from "@/lib/use-user";
import { Logo } from "./brand";

/**
 * App chrome. The link set is driven by role, not by a prop, so a candidate
 * can never be shown a recruiter route that would 403 on arrival.
 */
export function TopNav({ user }: { user: User }) {
  const pathname = usePathname();
  const router = useRouter();

  const links =
    user.role === "recruiter"
      ? [
          { href: "/recruiter/sessions", label: "Sessions" },
          { href: "/recruiter/review", label: "Review queue" },
          { href: "/recruiter/costs", label: "Costs" },
        ]
      : [
          // One entry: /interview lists every session and starts new ones.
          // The report and the live interview both belong under it.
          { href: "/interview", label: "My interviews", also: ["/reports"] },
        ];

  function signOut() {
    clearTokens();
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-surface/85 backdrop-blur-md supports-[backdrop-filter]:bg-surface/75">
      <div className="mx-auto flex h-[68px] w-full max-w-[1120px] items-center gap-4 px-4 sm:gap-7 sm:px-6">
        <Link href={homeFor(user)} aria-label="InterviewIQ home" className="shrink-0 rounded-[10px]">
          <Logo />
        </Link>

        <nav aria-label="Main" className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {links.map((link) => {
            const active =
              pathname.startsWith(link.href) ||
              ("also" in link && link.also!.some((p) => pathname.startsWith(p)));
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? "page" : undefined}
                className={`relative rounded-full px-3.5 py-2 text-[15px] whitespace-nowrap transition-colors duration-200 ${
                  active
                    ? "font-semibold text-accent-strong"
                    : "font-medium text-ink-2 hover:bg-accent-hover hover:text-ink"
                }`}
              >
                {active && (
                  // One pill that slides between links instead of popping.
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-full bg-accent-subtle"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="relative">{link.label}</span>
              </Link>
            );
          })}
        </nav>

        <span className="hidden rounded-full border border-line px-3 py-1 text-[13px] font-medium text-ink-2 capitalize sm:inline">
          {user.role}
        </span>
        <button
          onClick={signOut}
          // The visible text is just initials, which is what a screen reader
          // would announce without this — "E2, button". Name it for what it does.
          aria-label={`Sign out (${user.email})`}
          title={`Sign out ${user.email}`}
          className="group relative flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-full border border-line bg-canvas text-sm font-semibold text-ink transition-colors duration-200 hover:border-accent hover:bg-accent-subtle hover:text-accent-strong"
        >
          <span className="transition-opacity duration-200 group-hover:opacity-0">
            {user.email.slice(0, 2).toUpperCase()}
          </span>
          <LogOut
            aria-hidden="true"
            className="absolute size-[18px] opacity-0 transition-opacity duration-200 group-hover:opacity-100"
          />
        </button>
      </div>
    </header>
  );
}
