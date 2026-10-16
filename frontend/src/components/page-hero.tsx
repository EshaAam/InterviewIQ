"use client";

import { createContext, useContext, useLayoutEffect, type ReactNode } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { ChevronLeft } from "lucide-react";
import { EASE } from "./motion";

/**
 * Lets a page's hero tell the app chrome it is there, so the navbar can sit
 * transparent over it (as it does on the landing page) instead of as glass.
 * Outside the signed-in layout there is no provider and this is a no-op.
 */
export const HeroSlot = createContext<((present: boolean) => void) | null>(null);

const WIDTHS = {
  wide: "max-w-280",
  medium: "max-w-215",
  narrow: "max-w-155",
};

/**
 * The dark band every signed-in page opens with — the landing hero's surface,
 * grid and glow, at page-header size. It slides up under the fixed navbar
 * (the app wraps pages in nav-height top padding) so the band starts at the
 * very top of the window.
 */
export function PageHero({
  title,
  eyebrow,
  subtitle,
  actions,
  back,
  width = "wide",
  children,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  back?: { href: string; label: string };
  width?: keyof typeof WIDTHS;
  /** Extra hero content under the heading: stats, a score, a summary. */
  children?: ReactNode;
}) {
  const register = useContext(HeroSlot);
  // Layout effect, so the navbar flips before the first paint, not after it.
  useLayoutEffect(() => {
    register?.(true);
    return () => register?.(false);
  }, [register]);

  return (
    <section className="surface-hero relative isolate -mt-18 overflow-hidden pt-31 pb-12 sm:pt-34 sm:pb-14">
      <HeroBackdrop />
      <div className={`relative mx-auto w-full ${WIDTHS[width]} px-4 sm:px-6`}>
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: EASE }}
          className="flex flex-col gap-5"
        >
          {back && (
            <Link
              href={back.href}
              className="group inline-flex items-center gap-1.5 self-start rounded-full py-1 pr-3 text-sm font-semibold text-[#9ff0e6] transition-colors hover:text-white"
            >
              <ChevronLeft
                aria-hidden="true"
                className="size-4 transition-transform duration-200 group-hover:-translate-x-0.5"
              />
              {back.label}
            </Link>
          )}
          <div className="flex flex-wrap items-end justify-between gap-5">
            <div className="flex min-w-0 flex-col gap-3">
              {eyebrow && (
                <span className="inline-flex w-fit items-center gap-2 rounded-full border border-white/15 bg-white/6 px-3 py-1 text-xs font-semibold tracking-[0.08em] text-[#9ff0e6] uppercase backdrop-blur-sm">
                  <span className="size-1.5 rounded-full bg-glow" />
                  {eyebrow}
                </span>
              )}
              <h1 className="font-display text-[34px] leading-[1.06] font-bold tracking-[-0.03em] [overflow-wrap:anywhere] sm:text-[46px]">
                {title}
              </h1>
              {subtitle && (
                <p className="max-w-[64ch] text-[17px] leading-relaxed text-ink-on-dark">
                  {subtitle}
                </p>
              )}
            </div>
            {actions && <div className="flex shrink-0 flex-wrap items-center gap-3">{actions}</div>}
          </div>
        </motion.div>
        {children && (
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE, delay: 0.12 }}
            className="mt-9"
          >
            {children}
          </motion.div>
        )}
      </div>
    </section>
  );
}

/** A frosted stat tile for use inside a hero. */
export function HeroTile({
  value,
  label,
  icon,
}: {
  value: ReactNode;
  label: string;
  icon?: ReactNode;
}) {
  return (
    <div className="group flex min-w-0 flex-col gap-1 rounded-2xl border border-white/12 bg-white/6 px-4 py-3.5 backdrop-blur-sm transition-[background,transform,border-color] duration-250 ease-out-soft hover:-translate-y-0.5 hover:border-white/20 hover:bg-white/10">
      <span className="flex items-center gap-2 text-[13px] text-ink-on-dark">
        {icon && <span className="text-[#9ff0e6]">{icon}</span>}
        {label}
      </span>
      <span className="tabular truncate font-display text-[26px] leading-tight font-bold text-white">
        {value}
      </span>
    </div>
  );
}

/** The grid, glows and hairline the landing hero is drawn with. Decoration. */
function HeroBackdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 70% 90% at 70% 0%, black 25%, transparent 75%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 90% at 70% 0%, black 25%, transparent 75%)",
        }}
      />
      <motion.span
        className="absolute -top-48 right-[-8%] size-130 rounded-full bg-glow/22 blur-3xl"
        animate={{ x: [0, -50, 0], y: [0, 30, 0] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.span
        className="absolute -bottom-64 -left-24 size-110 rounded-full bg-accent/30 blur-3xl"
        animate={{ x: [0, 40, 0], y: [0, -24, 0] }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute inset-x-0 bottom-0 h-px bg-linear-to-r from-transparent via-glow/50 to-transparent" />
    </div>
  );
}
