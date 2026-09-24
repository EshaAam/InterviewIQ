/**
 * The primitive kit. Every one of these has a counterpart component in the
 * Figma file ("Design System" page) — same name, same variants.
 *
 * No "use client" here on purpose: these are pure presentational components,
 * so they compose into either a server or a client tree. The pages that own
 * state declare the boundary.
 */

import type { ReactNode } from "react";
import type { SessionState } from "@/lib/api";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

const BUTTON_STYLES: Record<ButtonVariant, string> = {
  primary: "bg-accent text-ink-inv hover:bg-accent-hover",
  secondary: "bg-surface text-ink border border-line hover:bg-subtle",
  ghost: "text-ink-2 hover:text-ink hover:bg-canvas",
  danger: "bg-bad text-ink-inv hover:brightness-95",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      {...props}
      className={`rounded-[10px] px-5 py-[11px] text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_STYLES[variant]} ${className}`}
    />
  );
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-card border border-line bg-surface shadow-[0_2px_6px_rgba(0,0,0,0.06)] ${className}`}
    >
      {children}
    </div>
  );
}

/** Small pill for anything that isn't a session state. */
export function Chip({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "ok" | "warn" | "bad" | "info";
}) {
  const tones = {
    neutral: "bg-canvas text-ink-2",
    accent: "bg-accent-subtle text-accent",
    ok: "bg-ok-subtle text-ok",
    warn: "bg-warn-subtle text-warn",
    bad: "bg-bad-subtle text-bad",
    info: "bg-info-subtle text-info",
  };
  return (
    <span
      className={`inline-flex items-center rounded-full px-[9px] py-1 text-[11px] font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

/**
 * One variant per SessionState. The label is the raw enum value on purpose —
 * a recruiter debugging a stuck session should see the same string the API
 * and the database use, not a prettified synonym.
 */
const STATE_TONE: Record<SessionState, { dot: string; text: string; bg: string }> = {
  CREATED: { dot: "bg-ink-2", text: "text-ink-2", bg: "bg-canvas" },
  PARSING: { dot: "bg-info", text: "text-info", bg: "bg-info-subtle" },
  GENERATING_QS: { dot: "bg-info", text: "text-info", bg: "bg-info-subtle" },
  READY: { dot: "bg-accent", text: "text-accent", bg: "bg-accent-subtle" },
  IN_PROGRESS: { dot: "bg-info", text: "text-info", bg: "bg-info-subtle" },
  EVALUATING: { dot: "bg-warn", text: "text-warn", bg: "bg-warn-subtle" },
  COMPLETED: { dot: "bg-ok", text: "text-ok", bg: "bg-ok-subtle" },
  NEEDS_HUMAN_REVIEW: { dot: "bg-warn", text: "text-warn", bg: "bg-warn-subtle" },
  FAILED: { dot: "bg-bad", text: "text-bad", bg: "bg-bad-subtle" },
  EXPIRED: { dot: "bg-ink-3", text: "text-ink-3", bg: "bg-canvas" },
};

export function StatusPill({ state }: { state: SessionState }) {
  const tone = STATE_TONE[state];
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-[5px] text-[11px] font-medium tracking-[0.4px] ${tone.bg} ${tone.text}`}
    >
      <span className={`size-1.5 rounded-full ${tone.dot}`} />
      {state}
    </span>
  );
}

export function SkillChip({ name, confidence }: { name: string; confidence: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-accent-subtle px-2.5 py-1.5 text-xs">
      <span className="font-medium text-accent">{name}</span>
      <span className="tabular text-ink-2">{confidence.toFixed(2)}</span>
    </span>
  );
}

export function Field({
  label,
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className={`flex flex-col gap-1.5 ${className}`}>
      <span className="text-xs font-medium text-ink-2">{label}</span>
      <input
        {...props}
        className="rounded-[10px] border border-line bg-surface px-3.5 py-[11px] text-sm text-ink outline-none placeholder:text-ink-3 focus:border-accent"
      />
    </label>
  );
}

export function ScoreBar({ topic, score }: { topic: string; score: number }) {
  const pct = Math.round(Math.min(Math.max(score, 0), 1) * 100);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between text-[13px]">
        <span className="font-medium text-ink">{topic}</span>
        <span className="tabular text-ink-2">{score.toFixed(2)}</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-canvas">
        <div
          className={`h-full rounded-full ${score < 0.5 ? "bg-bad" : "bg-accent"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

export function StatCard({
  label,
  value,
  caption,
}: {
  label: string;
  value: string;
  caption: string;
}) {
  return (
    <Card className="flex flex-1 flex-col gap-1.5 px-[18px] py-4">
      <span className="text-[11px] font-semibold tracking-[0.8px] text-ink-3">
        {label}
      </span>
      <span className="tabular text-[28px] font-semibold leading-8 text-ink">{value}</span>
      <span className="text-xs text-ink-2">{caption}</span>
    </Card>
  );
}

/** Centres a column of content at the same width every screen uses. */
export function Shell({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-[880px] px-6 py-11">{children}</div>;
}

export function PageHeading({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-[-0.4px] text-ink">{title}</h1>
        {subtitle && <p className="max-w-[640px] text-[13px] text-ink-2">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2.5">{actions}</div>}
    </div>
  );
}
