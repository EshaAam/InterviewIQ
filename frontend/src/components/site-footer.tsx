"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUp, ArrowUpRight, Check, Copy, Mail } from "lucide-react";
import { Logo } from "./brand";
import { EASE, Reveal } from "./motion";

const OWNER = { name: "Ekramul Esham", initials: "EE", email: "ekramul.esham@gmail.com" };

const COLUMNS = [
  {
    title: "Product",
    links: [
      { href: "/#how", label: "How it works" },
      { href: "/#grading", label: "Grading" },
      { href: "/#recruiters", label: "For recruiters" },
    ],
  },
  {
    title: "Account",
    links: [
      { href: "/interview", label: "My interviews" },
      { href: "/login", label: "Sign in" },
      { href: "/login?next=%2Finterview", label: "Start an interview" },
    ],
  },
];

/** The site footer, shared by the landing page and every signed-in page. */
export function SiteFooter() {
  return (
    <footer className="relative isolate overflow-hidden bg-[#0a2c32] text-white">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent via-glow/60 to-transparent" />
        <motion.span
          className="absolute -top-56 left-1/2 size-140 -translate-x-1/2 rounded-full bg-glow/12 blur-3xl"
          animate={{ scale: [1, 1.12, 1], opacity: [0.8, 1, 0.8] }}
          transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
        />
      </div>

      <div className="mx-auto grid w-full max-w-280 gap-10 px-4 pt-14 pb-10 sm:px-6 md:grid-cols-2 lg:grid-cols-[1.2fr_0.7fr_0.7fr_1.3fr] lg:gap-10">
        <Reveal className="flex flex-col gap-4">
          <Link href="/" aria-label="InterviewIQ home" className="w-fit rounded-[10px]">
            <Logo tone="light" />
          </Link>
          <p className="max-w-72 text-sm leading-relaxed text-ink-on-dark">
            Resume-driven skills interviews. Every answer graded twice, and a person settles
            anything the graders disagree on.
          </p>
        </Reveal>

        {COLUMNS.map((column, i) => (
          <Reveal key={column.title} delay={0.06 * (i + 1)} className="flex flex-col gap-3.5">
            <h2 className="text-xs font-semibold tracking-[0.14em] text-[#9ff0e6] uppercase">
              {column.title}
            </h2>
            <ul className="flex flex-col gap-2">
              {column.links.map((link) => (
                <li key={link.label}>
                  <Link
                    href={link.href}
                    className="group inline-flex items-center gap-1 text-sm text-ink-on-dark transition-colors duration-200 hover:text-white"
                  >
                    <span className="relative">
                      {link.label}
                      <span className="absolute -bottom-0.5 left-0 h-px w-full origin-left scale-x-0 bg-glow transition-transform duration-300 ease-out-soft group-hover:scale-x-100" />
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </Reveal>
        ))}

        <Reveal delay={0.2}>
          <OwnerCard />
        </Reveal>
      </div>

      <div className="mx-auto flex w-full max-w-280 flex-col-reverse items-center justify-between gap-4 border-t border-white/10 px-4 py-4 text-sm text-ink-on-dark sm:flex-row sm:px-6">
        <p>
          © <span suppressHydrationWarning>{new Date().getFullYear()}</span> InterviewIQ · Built by{" "}
          {OWNER.name}
        </p>
        <button
          type="button"
          onClick={() => window.scrollTo({ top: 0 })}
          className="group inline-flex cursor-pointer items-center gap-2 rounded-full border border-white/15 px-4 py-1.5 font-medium text-white transition-[background,border-color] duration-250 hover:border-white/35 hover:bg-white/8"
        >
          Back to top
          <ArrowUp
            aria-hidden="true"
            className="size-4 transition-transform duration-250 group-hover:-translate-y-0.5"
          />
        </button>
      </div>

      {/* The wordmark as a faint watermark behind everything: texture, not a
          second logo competing with the real one, and it adds no height. */}
      <motion.div
        aria-hidden="true"
        initial={{ opacity: 0, y: "20%" }}
        whileInView={{ opacity: 1, y: "0%" }}
        viewport={{ once: true }}
        transition={{ duration: 1.1, ease: EASE }}
        className="pointer-events-none absolute inset-x-0 bottom-0 -z-10 translate-y-[18%] text-center font-display text-[15vw] leading-none font-bold tracking-[-0.06em] whitespace-nowrap select-none"
      >
        <span className="bg-linear-to-b from-white/5 to-white/0 bg-clip-text text-transparent">
          InterviewIQ
        </span>
      </motion.div>
    </footer>
  );
}

/** Who owns the project, and a one-click way to reach them. */
function OwnerCard() {
  const [copied, setCopied] = useState(false);
  const reset = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(reset.current), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(OWNER.email);
    } catch {
      return; // no clipboard permission: the mailto link still works
    }
    setCopied(true);
    window.clearTimeout(reset.current);
    reset.current = window.setTimeout(() => setCopied(false), 1800);
  }

  return (
    <div className="group/card relative overflow-hidden rounded-2xl border border-white/12 bg-white/5 p-5 backdrop-blur-sm transition-[border-color,background] duration-300 hover:border-white/20 hover:bg-white/7">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-20 -right-16 size-48 rounded-full bg-glow/25 blur-3xl transition-opacity duration-500 group-hover/card:opacity-100 sm:opacity-60"
      />
      <h2 className="relative text-xs font-semibold tracking-[0.14em] text-[#9ff0e6] uppercase">
        Owner
      </h2>
      <div className="relative mt-3 flex items-center gap-3.5">
        <span className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-linear-to-br from-[#9ff0e6] via-glow to-accent font-display text-base font-bold text-brand shadow-[0_12px_30px_-12px_rgba(43,179,166,0.8)] transition-transform duration-300 ease-out-soft group-hover/card:-rotate-6">
          {OWNER.initials}
        </span>
        <div className="flex min-w-0 flex-col">
          <span className="text-[17px] font-semibold text-white">{OWNER.name}</span>
          <span className="text-sm text-ink-on-dark">Builds and maintains InterviewIQ</span>
        </div>
      </div>

      <div className="relative mt-4 flex items-center gap-2">
        <a
          href={`mailto:${OWNER.email}`}
          className="group/mail flex min-h-11 min-w-0 flex-1 items-center gap-2.5 rounded-full bg-white px-4 text-sm font-semibold text-brand transition-[background,transform,box-shadow] duration-250 ease-out-soft hover:-translate-y-px hover:bg-accent-soft hover:shadow-[0_12px_28px_-14px_rgba(43,179,166,0.8)]"
        >
          <Mail aria-hidden="true" className="size-4 shrink-0" />
          <span className="truncate">{OWNER.email}</span>
          <ArrowUpRight
            aria-hidden="true"
            className="ml-auto size-4 shrink-0 transition-transform duration-250 group-hover/mail:translate-x-0.5 group-hover/mail:-translate-y-0.5"
          />
        </a>
        <button
          type="button"
          onClick={copy}
          aria-label={copied ? "Email address copied" : "Copy email address"}
          title={copied ? "Copied" : "Copy email address"}
          className="flex size-11 shrink-0 cursor-pointer items-center justify-center rounded-full border border-white/20 text-white transition-[background,border-color] duration-200 hover:border-white/40 hover:bg-white/10"
        >
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={copied ? "done" : "copy"}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.5 }}
              transition={{ duration: 0.18 }}
            >
              {copied ? (
                <Check aria-hidden="true" className="size-4 text-glow" />
              ) : (
                <Copy aria-hidden="true" className="size-4" />
              )}
            </motion.span>
          </AnimatePresence>
        </button>
      </div>
      <span aria-live="polite" className="sr-only">
        {copied ? "Email address copied" : ""}
      </span>
    </div>
  );
}
