"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, useMotionValueEvent, useScroll } from "motion/react";
import { ArrowRight, Upload } from "lucide-react";
import type { User } from "@/lib/auth";
import { homeFor, loginHref } from "@/lib/use-user";
import { Logo } from "@/components/brand";
import { EASE } from "@/components/motion";

const LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#grading", label: "Grading" },
  { href: "#recruiters", label: "For recruiters" },
];

/**
 * The landing page's chrome. It starts transparent over the dark hero and
 * turns into a frosted pill once the page scrolls, so the colours flip with
 * it: light-on-teal at the top, ink-on-glass below.
 *
 * Who is signed in decides the right-hand side. While `/auth/me` is still
 * answering (a sleeping backend can take a minute) it shows "Sign in", which
 * is harmless: the sign-in page forwards anyone who already has a session.
 */
export function PublicNav({ user, onStart }: { user: User | null; onStart: () => void }) {
  const { scrollY } = useScroll();
  const [scrolled, setScrolled] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  useMotionValueEvent(scrollY, "change", (y) => setScrolled(y > 24));

  const pill =
    // No display class here: callers add `inline-flex` (or `hidden sm:inline-flex`),
    // since a bare `inline-flex` would override `hidden`.
    "min-h-10 items-center gap-1.5 rounded-full whitespace-nowrap px-4 text-sm font-semibold transition-[background,border-color,color,box-shadow,transform] duration-250 ease-out-soft";

  return (
    <motion.header
      initial={{ y: -24, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.7, ease: EASE, delay: 0.1 }}
      className="fixed inset-x-0 top-0 z-50 px-3 pt-3 sm:px-6"
    >
      <div
        className={`mx-auto flex h-15 max-w-280 items-center gap-4 rounded-full border pr-2 pl-4 transition-[background-color,border-color,box-shadow] duration-300 ease-out-soft sm:pl-5 ${
          scrolled
            ? "border-line/80 bg-surface/80 shadow-[0_12px_32px_-18px_rgba(15,46,53,0.4)] backdrop-blur-xl"
            : "border-transparent bg-transparent"
        }`}
      >
        <Link href="/" aria-label="InterviewIQ home" className="shrink-0 rounded-[10px]">
          <Logo tone={scrolled ? "dark" : "light"} />
        </Link>

        <nav
          aria-label="Sections"
          className="hidden flex-1 items-center justify-center gap-1 md:flex"
          onMouseLeave={() => setHovered(null)}
        >
          {LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              onMouseEnter={() => setHovered(link.href)}
              onFocus={() => setHovered(link.href)}
              onBlur={() => setHovered(null)}
              className={`relative rounded-full px-4 py-2 text-[15px] font-medium transition-colors duration-200 ${
                scrolled ? "text-ink-2 hover:text-ink" : "text-ink-on-dark hover:text-white"
              }`}
            >
              {hovered === link.href && (
                // One highlight that glides between links instead of blinking.
                <motion.span
                  layoutId="public-nav-hover"
                  className={`absolute inset-0 rounded-full ${scrolled ? "bg-accent-hover" : "bg-white/10"}`}
                  transition={{ type: "spring", stiffness: 450, damping: 36 }}
                />
              )}
              <span className="relative">{link.label}</span>
            </a>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2 md:ml-0">
          {user ? (
            <Link
              href={homeFor(user)}
              className={`group inline-flex ${pill} ${
                scrolled ? "btn-brand" : "bg-white text-brand hover:bg-accent-soft"
              }`}
            >
              {user.role === "recruiter" ? "Open review queue" : "My interviews"}
              <ArrowRight
                aria-hidden="true"
                className="size-4 transition-transform duration-250 group-hover:translate-x-0.5"
              />
            </Link>
          ) : (
            <>
              <Link
                href={loginHref()}
                className={`inline-flex ${pill} border ${
                  scrolled
                    ? "border-line-strong text-ink hover:border-accent hover:bg-accent-soft hover:text-accent-strong"
                    : "border-white/25 text-white hover:border-white/50 hover:bg-white/10"
                }`}
              >
                Sign in
              </Link>
              <button
                type="button"
                onClick={onStart}
                className={`hidden cursor-pointer sm:inline-flex ${pill} ${
                  scrolled
                    ? "btn-brand"
                    : "bg-white text-brand shadow-[0_8px_24px_-12px_rgba(0,0,0,0.5)] hover:-translate-y-px hover:bg-accent-soft"
                }`}
              >
                <Upload aria-hidden="true" className="size-4" />
                Upload resume
              </button>
            </>
          )}
        </div>
      </div>
    </motion.header>
  );
}
