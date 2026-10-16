"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion, useMotionValueEvent, useScroll } from "motion/react";
import { House, LayoutList, LogOut, Menu, Upload, X } from "lucide-react";
import type { User } from "@/lib/auth";
import { homeFor, loginHref, useSignOut } from "@/lib/use-user";
import { Logo } from "./brand";
import { EASE } from "./motion";

type NavLink = { href: string; label: string; match?: string[] };

/**
 * The link set is driven by who is signed in, so a candidate is never shown a
 * recruiter route that would 403 on arrival. Section anchors point at the
 * landing page, as `#id` when already on it and `/#id` from anywhere else.
 */
function linksFor(user: User | null, onLanding: boolean): NavLink[] {
  const section = (id: string) => (onLanding ? `#${id}` : `/#${id}`);
  if (!user) {
    return [
      { href: section("how"), label: "How it works" },
      { href: section("grading"), label: "Grading" },
      { href: section("recruiters"), label: "For recruiters" },
    ];
  }
  if (user.role === "recruiter") {
    return [
      { href: "/", label: "Home" },
      { href: "/recruiter/sessions", label: "Sessions" },
      { href: "/recruiter/review", label: "Review queue" },
      { href: "/recruiter/costs", label: "Costs" },
    ];
  }
  return [
    { href: "/", label: "Home" },
    { href: section("how"), label: "How it works" },
    // The report and the live interview both belong under "My interviews".
    { href: "/interview", label: "My interviews", match: ["/interview", "/reports"] },
  ];
}

function isActive(link: NavLink, pathname: string): boolean {
  if (link.href.includes("#")) return false;
  if (link.href === "/") return pathname === "/";
  return (link.match ?? [link.href]).some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/**
 * The one navbar, on the landing page and every signed-in page alike: a
 * floating pill that is transparent over a dark hero and turns to frosted
 * glass once the page scrolls (or when there's no hero underneath at all).
 */
export function SiteNav({
  user,
  overDark = false,
  onStart,
}: {
  user: User | null;
  /** A dark hero sits under the nav at the top of this page. */
  overDark?: boolean;
  /** What "Upload resume" does; without it, the button links to sign-in. */
  onStart?: () => void;
}) {
  const pathname = usePathname();
  const links = linksFor(user, pathname === "/");
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 24));

  // A navigation closes the phone menu. Adjusting state during render (not in
  // an effect) is React's recommended way to reset on a prop change.
  const [shownPath, setShownPath] = useState(pathname);
  if (pathname !== shownPath) {
    setShownPath(pathname);
    setMenuOpen(false);
  }

  const light = overDark && !scrolled && !menuOpen;
  const pill =
    "min-h-10 items-center gap-1.5 rounded-full px-4 text-sm font-semibold whitespace-nowrap " +
    "transition-[background,border-color,color,box-shadow,transform] duration-250 ease-out-soft";
  const uploadClass = `hidden cursor-pointer sm:inline-flex ${pill} ${
    light
      ? "bg-white text-brand shadow-[0_8px_24px_-12px_rgba(0,0,0,0.5)] hover:-translate-y-px hover:bg-accent-soft"
      : "btn-brand"
  }`;

  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.7, ease: EASE, delay: 0.05 }}
      className="fixed inset-x-0 top-0 z-50 px-3 pt-3 sm:px-6"
    >
      <div className="relative mx-auto max-w-280">
        <div
          className={`flex h-15 items-center gap-3 rounded-full border pr-2 pl-4 transition-[background-color,border-color,box-shadow] duration-300 ease-out-soft sm:gap-4 sm:pl-5 ${
            light
              ? "border-transparent bg-transparent"
              : "border-line/80 bg-surface/85 shadow-[0_12px_32px_-18px_rgba(15,46,53,0.4)] backdrop-blur-xl"
          }`}
        >
          <Link href="/" aria-label="InterviewIQ home" className="shrink-0 rounded-[10px]">
            <Logo tone={light ? "light" : "dark"} />
          </Link>

          <nav
            aria-label="Main"
            className="hidden flex-1 items-center justify-center gap-1 md:flex"
            onMouseLeave={() => setHovered(null)}
          >
            {links.map((link) => {
              const active = isActive(link, pathname);
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  aria-current={active ? "page" : undefined}
                  onMouseEnter={() => setHovered(link.href)}
                  onFocus={() => setHovered(link.href)}
                  onBlur={() => setHovered(null)}
                  className={`relative rounded-full px-4 py-2 text-[15px] transition-colors duration-200 ${
                    active ? "font-semibold" : "font-medium"
                  } ${
                    light
                      ? active
                        ? "text-white"
                        : "text-ink-on-dark hover:text-white"
                      : active
                        ? "text-accent-strong"
                        : "text-ink-2 hover:text-ink"
                  }`}
                >
                  {active && (
                    // The current page's pill slides between links on navigation.
                    <motion.span
                      layoutId="site-nav-active"
                      className={`absolute inset-0 rounded-full ${light ? "bg-white/15" : "bg-accent-subtle"}`}
                      transition={{ type: "spring", stiffness: 420, damping: 34 }}
                    />
                  )}
                  {hovered === link.href && !active && (
                    <motion.span
                      layoutId="site-nav-hover"
                      className={`absolute inset-0 rounded-full ${light ? "bg-white/10" : "bg-accent-hover"}`}
                      transition={{ type: "spring", stiffness: 450, damping: 36 }}
                    />
                  )}
                  <span className="relative">{link.label}</span>
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-2 md:ml-0">
            {user ? (
              <AccountMenu user={user} light={light} />
            ) : (
              <>
                <Link
                  href={loginHref()}
                  className={`inline-flex ${pill} border ${
                    light
                      ? "border-white/25 text-white hover:border-white/50 hover:bg-white/10"
                      : "border-line-strong text-ink hover:border-accent hover:bg-accent-soft hover:text-accent-strong"
                  }`}
                >
                  Sign in
                </Link>
                {onStart ? (
                  <button type="button" onClick={onStart} className={uploadClass}>
                    <Upload aria-hidden="true" className="size-4" />
                    Upload resume
                  </button>
                ) : (
                  <Link href={loginHref("/interview")} className={uploadClass}>
                    <Upload aria-hidden="true" className="size-4" />
                    Upload resume
                  </Link>
                )}
              </>
            )}

            <button
              type="button"
              aria-label={menuOpen ? "Close menu" : "Open menu"}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
              className={`relative flex size-10 cursor-pointer items-center justify-center rounded-full transition-colors duration-200 md:hidden ${
                light ? "text-white hover:bg-white/10" : "text-ink hover:bg-accent-hover"
              }`}
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={menuOpen ? "close" : "open"}
                  initial={{ opacity: 0, rotate: -90, scale: 0.6 }}
                  animate={{ opacity: 1, rotate: 0, scale: 1 }}
                  exit={{ opacity: 0, rotate: 90, scale: 0.6 }}
                  transition={{ duration: 0.2 }}
                >
                  {menuOpen ? (
                    <X aria-hidden="true" className="size-5" />
                  ) : (
                    <Menu aria-hidden="true" className="size-5" />
                  )}
                </motion.span>
              </AnimatePresence>
            </button>
          </div>
        </div>

        <AnimatePresence>
          {menuOpen && (
            <motion.nav
              aria-label="Main (mobile)"
              initial={{ opacity: 0, y: -8, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: -8, scale: 0.98 }}
              transition={{ duration: 0.25, ease: EASE }}
              style={{ transformOrigin: "top center" }}
              className="absolute inset-x-0 top-[calc(100%+8px)] rounded-3xl border border-line bg-surface/95 p-2 shadow-[0_24px_48px_-20px_rgba(15,46,53,0.45)] backdrop-blur-xl md:hidden"
            >
              {links.map((link, i) => {
                const active = isActive(link, pathname);
                return (
                  <motion.div
                    key={link.href}
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.25, ease: EASE, delay: 0.03 * i }}
                  >
                    <Link
                      href={link.href}
                      onClick={() => setMenuOpen(false)}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center rounded-2xl px-4 py-3 text-base font-medium transition-colors ${
                        active
                          ? "bg-accent-subtle font-semibold text-accent-strong"
                          : "text-ink hover:bg-accent-hover"
                      }`}
                    >
                      {link.label}
                    </Link>
                  </motion.div>
                );
              })}
              {!user && (
                <Link
                  href={loginHref("/interview")}
                  onClick={(e) => {
                    if (!onStart) return;
                    e.preventDefault();
                    setMenuOpen(false);
                    onStart();
                  }}
                  className="btn-brand mt-2 flex min-h-12 items-center justify-center gap-2 rounded-full text-[15px] font-semibold"
                >
                  <Upload aria-hidden="true" className="size-4" />
                  Upload your resume
                </Link>
              )}
            </motion.nav>
          )}
        </AnimatePresence>
      </div>
    </motion.header>
  );
}

/** Initials that open a small account card: who you are, where to go, sign out. */
function AccountMenu({ user, light }: { user: User; light: boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const signOut = useSignOut();
  const initials = user.email.slice(0, 2).toUpperCase();

  // Close on a click elsewhere or Escape, the way a native menu does.
  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const item =
    "flex w-full cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-colors duration-150";

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account menu (${user.email})`}
        className={`flex size-11 cursor-pointer items-center justify-center rounded-full text-sm font-semibold transition-[background,box-shadow,transform] duration-200 hover:scale-105 ${
          light
            ? "bg-white/12 text-white ring-1 ring-white/25 hover:bg-white/20"
            : "bg-accent-subtle text-accent-strong ring-1 ring-accent-ring hover:ring-accent-mid"
        } ${open ? "ring-2" : ""}`}
      >
        {initials}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            role="menu"
            aria-label="Account"
            initial={{ opacity: 0, y: -6, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.96 }}
            transition={{ duration: 0.2, ease: EASE }}
            style={{ transformOrigin: "top right" }}
            className="absolute top-[calc(100%+12px)] right-0 w-72 rounded-2xl border border-line bg-surface/95 p-2 text-ink shadow-[0_24px_48px_-20px_rgba(15,46,53,0.45)] backdrop-blur-xl"
          >
            <div className="flex items-center gap-3 px-3 py-3">
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-glow to-accent font-display text-sm font-bold text-white">
                {initials}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-sm font-semibold" title={user.email}>
                  {user.email}
                </span>
                <span className="text-xs text-ink-3">
                  {user.role === "recruiter" ? "Recruiter account" : "Candidate account"}
                </span>
              </span>
            </div>
            <div className="my-1 h-px bg-line-soft" />
            <Link
              role="menuitem"
              href={homeFor(user)}
              onClick={() => setOpen(false)}
              className={`${item} hover:bg-accent-hover`}
            >
              <LayoutList aria-hidden="true" className="size-4 text-accent" />
              {user.role === "recruiter" ? "Review queue" : "My interviews"}
            </Link>
            <Link
              role="menuitem"
              href="/"
              onClick={() => setOpen(false)}
              className={`${item} hover:bg-accent-hover`}
            >
              <House aria-hidden="true" className="size-4 text-accent" />
              Home
            </Link>
            <div className="my-1 h-px bg-line-soft" />
            <button
              type="button"
              role="menuitem"
              onClick={signOut}
              className={`${item} text-bad hover:bg-bad-subtle`}
            >
              <LogOut aria-hidden="true" className="size-4" />
              Sign out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
