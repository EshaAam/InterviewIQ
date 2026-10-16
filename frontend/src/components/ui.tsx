/**
 * The primitive kit, built to docs/InterviewIQ Candidate Redesign.html.
 *
 * No "use client" here on purpose: these are presentational components, so
 * they compose into either a server or a client tree. The animated pieces
 * come from `./motion`, which is the client boundary.
 */

import type { ReactNode } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ChevronLeft,
  CircleAlert,
  CircleCheck,
  Info,
  Loader2,
} from "lucide-react";
import type { SessionState, CitedSource } from "@/lib/api";
import { toHundred } from "@/lib/format";
import { BarFill, FadeIn, PulseDot } from "./motion";
import { PageHero } from "./page-hero";

// --- Buttons ---------------------------------------------------------------

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_BASE =
  "inline-flex items-center justify-center gap-2 rounded-full font-semibold whitespace-nowrap " +
  "transition-[background,border-color,box-shadow,transform,color] duration-200 ease-out-soft " +
  "disabled:cursor-not-allowed disabled:opacity-55 cursor-pointer";

const BUTTON_VARIANTS: Record<ButtonVariant, string> = {
  primary: "btn-brand",
  secondary:
    "border border-line-strong bg-surface text-ink hover:enabled:border-accent hover:enabled:bg-[#f0f8f7] " +
    "hover:enabled:text-accent-strong hover:enabled:shadow-[0_6px_16px_-10px_rgba(10,117,112,0.6)]",
  ghost: "text-ink-2 hover:enabled:bg-accent-hover hover:enabled:text-ink",
  danger: "bg-bad text-ink-inv hover:enabled:brightness-110 hover:enabled:-translate-y-px",
};

const BUTTON_SIZES: Record<ButtonSize, string> = {
  sm: "min-h-9 px-3.5 text-[13px]",
  md: "min-h-11.5 px-5.5 text-[15px]",
  lg: "min-h-12 px-6 text-[15px]",
};

/** The class string for a button — for a `<Link>` that should look like one. */
export function buttonClass(
  variant: ButtonVariant = "primary",
  size: ButtonSize = "md",
  className = "",
): string {
  return `${BUTTON_BASE} ${BUTTON_VARIANTS[variant]} ${BUTTON_SIZES[size]} ${className}`;
}

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  className = "",
  children,
  disabled,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Shows a spinner before the label; the label itself says what's happening. */
  loading?: boolean;
}) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={buttonClass(variant, size, className)}
    >
      {loading && <Loader2 aria-hidden="true" className="size-4 animate-spin" />}
      {children}
    </button>
  );
}

// --- Surfaces --------------------------------------------------------------

export function Card({
  children,
  className = "",
  as: Tag = "div",
  ...rest
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "section" | "aside" | "article";
} & React.HTMLAttributes<HTMLElement>) {
  return (
    <Tag
      {...rest}
      className={`rounded-card border border-line bg-surface shadow-card ${className}`}
    >
      {children}
    </Tag>
  );
}

/** Centres a page at one of three widths: dashboards, focused tasks, single cards. */
export function Shell({
  children,
  width = "wide",
  className = "",
}: {
  children: ReactNode;
  width?: "wide" | "medium" | "narrow";
  className?: string;
}) {
  const max = { wide: "max-w-280", medium: "max-w-215", narrow: "max-w-155" }[width];
  return (
    <div className={`mx-auto w-full ${max} px-4 pt-10 pb-18 sm:px-6 sm:pt-12 ${className}`}>
      <FadeIn>{children}</FadeIn>
    </div>
  );
}

export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="group inline-flex items-center gap-1.5 self-start text-sm font-semibold text-accent transition-colors hover:text-brand"
    >
      <ChevronLeft
        aria-hidden="true"
        className="size-4 transition-transform duration-200 group-hover:-translate-x-0.5"
      />
      {children}
    </Link>
  );
}

// --- Labels and pills ------------------------------------------------------

export type Tone = "neutral" | "accent" | "ok" | "warn" | "bad" | "info";

const TONES: Record<Tone, string> = {
  neutral: "bg-canvas text-ink-2",
  accent: "bg-accent-subtle text-accent-strong",
  ok: "bg-ok-subtle text-ok",
  warn: "bg-warn-subtle text-warn",
  bad: "bg-bad-subtle text-bad",
  info: "bg-info-subtle text-info",
};

/** Small pill for anything that isn't a session state. */
export function Chip({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={`inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.75 text-xs font-semibold ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/** A skill or topic name, quieter than a chip. */
export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-md bg-canvas px-2.5 py-0.5 text-[13px] text-ink-2">{children}</span>
  );
}

/**
 * Plain-English name for each SessionState, for every screen a person reads.
 *
 * This replaced showing the raw enum. The original reasoning — a recruiter
 * debugging a stuck session should see the string the API and database use —
 * still holds, so the raw value is kept on the pill as a hover title rather
 * than thrown away. But "NEEDS_HUMAN_REVIEW" and "EVALUATING" in front of a
 * candidate read like an error code, and the person most likely to be looking
 * at a stuck session is the one waiting on it, not the one debugging it.
 *
 * `Record` keeps this exhaustive: a new backend state fails the build here
 * until it has a name, exactly as STATE_TONE does for its colour.
 */
export const STATE_LABEL: Record<SessionState, string> = {
  CREATED: "Starting",
  PARSING: "Reading resume",
  GENERATING_QS: "Writing questions",
  READY: "Ready",
  IN_PROGRESS: "In progress",
  EVALUATING: "Scoring",
  COMPLETED: "Completed",
  NEEDS_HUMAN_REVIEW: "Needs review",
  FAILED: "Failed",
  EXPIRED: "Expired",
};

/** One tone per SessionState. */
const STATE_TONE: Record<SessionState, Tone> = {
  CREATED: "info",
  PARSING: "info",
  GENERATING_QS: "info",
  READY: "accent",
  IN_PROGRESS: "accent",
  EVALUATING: "info",
  COMPLETED: "ok",
  NEEDS_HUMAN_REVIEW: "warn",
  FAILED: "bad",
  EXPIRED: "bad",
};

/** States where something is happening right now — they get a live dot. */
const LIVE: ReadonlySet<SessionState> = new Set([
  "CREATED",
  "PARSING",
  "GENERATING_QS",
  "IN_PROGRESS",
  "EVALUATING",
]);

export function StatusPill({ state }: { state: SessionState }) {
  return (
    <span
      // The raw value stays reachable for whoever is matching this against an
      // API response or a database row.
      title={state}
      className={`inline-flex w-fit shrink-0 items-center gap-1.5 rounded-full px-2.5 py-0.75 text-xs font-semibold tracking-[0.02em] ${TONES[STATE_TONE[state]]}`}
    >
      {LIVE.has(state) && <PulseDot />}
      {STATE_LABEL[state]}
    </span>
  );
}

// --- Form fields -----------------------------------------------------------

/** Shared look for text inputs and textareas. */
export const FIELD_CLASS =
  "w-full rounded-control border border-line-strong bg-field px-4 py-3 text-[15px] text-ink " +
  "outline-none transition-[border-color,box-shadow,background] duration-200 placeholder:text-ink-3 " +
  "hover:border-accent-mid focus:border-accent focus:bg-surface focus:shadow-[0_0_0_4px_var(--color-accent-ring)] " +
  "disabled:opacity-60";

export function Field({
  label,
  hint,
  className = "",
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string; hint?: ReactNode }) {
  return (
    <label className={`flex flex-col gap-2 ${className}`}>
      <span className="text-sm font-semibold text-ink">{label}</span>
      <input {...props} className={FIELD_CLASS} />
      {hint && <span className="text-[13px] text-ink-3">{hint}</span>}
    </label>
  );
}

// --- Scores ----------------------------------------------------------------

/** A topic score on the 0–100 scale the candidate reads, with a growing bar. */
export function ScoreBar({
  topic,
  score,
  delay = 0,
}: {
  topic: string;
  score: number;
  delay?: number;
}) {
  const pct = toHundred(score);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-4">
        <span className="font-semibold text-ink">{topic}</span>
        <span className="tabular font-semibold text-ink">
          {pct}
          <span className="font-normal text-ink-3">/100</span>
        </span>
      </div>
      {/* A meter, so assistive tech reads it as "topic, 72 percent" rather
          than skipping an unlabelled div. */}
      <div
        role="meter"
        aria-label={topic}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="h-2.5 w-full overflow-hidden rounded-full bg-track"
      >
        <BarFill
          pct={pct}
          delay={delay}
          className="h-full rounded-full bg-linear-to-r from-accent to-glow"
        />
      </div>
    </div>
  );
}

/** A small labelled bar — skill confidence on the new-interview card. */
export function MeterRow({
  label,
  value,
  delay = 0,
}: {
  label: string;
  /** 0..1 */
  value: number;
  delay?: number;
}) {
  const pct = toHundred(value);
  return (
    <div className="flex items-center gap-3">
      <span className="w-28 truncate text-sm text-ink" title={label}>
        {label}
      </span>
      <div
        role="meter"
        aria-label={`${label} confidence`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        className="h-1.5 flex-1 overflow-hidden rounded-full bg-track"
      >
        <BarFill pct={pct} delay={delay} className="h-full rounded-full bg-accent" />
      </div>
      <span className="tabular w-9 text-right text-[13px] text-ink-2">{value.toFixed(2)}</span>
    </div>
  );
}

export function StatCard({
  label,
  value,
  caption,
  icon,
}: {
  label: string;
  value: ReactNode;
  caption: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <Card className="group flex min-w-45 flex-1 flex-col gap-1.5 px-5 py-4.5 transition-[transform,box-shadow,border-color] duration-250 ease-out-soft hover:-translate-y-0.5 hover:border-accent-mid hover:shadow-lift">
      <span className="flex items-center justify-between text-xs font-semibold tracking-[0.06em] text-ink-3 uppercase">
        {label}
        {icon && (
          <span className="flex size-8 items-center justify-center rounded-[10px] bg-accent-subtle text-accent transition-transform duration-300 group-hover:-rotate-6">
            {icon}
          </span>
        )}
      </span>
      <span className="tabular font-display text-[30px] leading-9 font-bold text-ink">{value}</span>
      <span className="text-[13px] text-ink-2">{caption}</span>
    </Card>
  );
}

/** A labelled number in a tinted box — one side of a score comparison. */
export function ScoreBox({
  label,
  value,
  caption,
  tone,
}: {
  label: string;
  value: string;
  caption: string;
  /** A text colour class, e.g. "text-bad". */
  tone: string;
}) {
  return (
    <div className="flex min-w-35 flex-1 flex-col gap-1 rounded-[14px] bg-canvas px-4 py-3.5">
      <span className="text-[11px] font-semibold tracking-[0.06em] text-ink-3 uppercase">
        {label}
      </span>
      <span className={`tabular font-display text-[24px] leading-8 font-bold ${tone}`}>
        {value}
      </span>
      <span className="text-xs text-ink-3">{caption}</span>
    </div>
  );
}

// --- Feedback --------------------------------------------------------------

const NOTICE_STYLE: Record<
  "info" | "warn" | "bad" | "ok" | "neutral",
  { box: string; icon: ReactNode }
> = {
  neutral: {
    box: "bg-canvas text-ink-2",
    icon: <Info aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-accent" />,
  },
  info: {
    box: "bg-info-subtle text-ink-2 border border-[#c9d9ee]",
    icon: <Info aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-info" />,
  },
  warn: {
    box: "bg-warn-subtle text-warn-deep border border-warn-line",
    icon: <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-warn" />,
  },
  bad: {
    box: "bg-bad-subtle text-bad border border-[#efc6c2]",
    icon: <AlertTriangle aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-bad" />,
  },
  ok: {
    box: "bg-ok-subtle text-ink-2 border border-[#bfe0cc]",
    icon: <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-ok" />,
  },
};

/** A callout box: an icon, an optional bold title, and a sentence or two. */
export function Notice({
  tone = "neutral",
  title,
  children,
  action,
  role,
}: {
  tone?: keyof typeof NOTICE_STYLE;
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  role?: "status" | "alert";
}) {
  const style = NOTICE_STYLE[tone];
  return (
    <div role={role} className={`flex items-start gap-3 rounded-[14px] px-4 py-3.5 ${style.box}`}>
      {style.icon}
      <div className="flex min-w-0 flex-1 flex-col gap-0.5 text-sm">
        {title && <span className="font-semibold">{title}</span>}
        {children && <span>{children}</span>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}

/** The red line every page uses for a failed request. */
export function ErrorBanner({ message }: { message: string }) {
  return (
    <Notice tone="bad" role="alert">
      {message}
    </Notice>
  );
}

export function Spinner({ label = "Loading…" }: { label?: string }) {
  return (
    <span role="status" className="inline-flex items-center gap-2.5 text-sm text-ink-3">
      <Loader2 aria-hidden="true" className="size-4 animate-spin text-accent" />
      {label}
    </span>
  );
}

/** A shimmering placeholder block for content that is on its way. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={`animate-pulse rounded-control bg-linear-to-r from-track via-line-soft to-track ${className}`}
    />
  );
}

/**
 * A whole page that is waiting on its first fetch. Pages that open with a
 * `PageHero` load with a skeleton one, so the dark band (and the navbar over
 * it) doesn't flash light and then flip when the data lands.
 */
export function PageLoading({
  width = "wide",
  hero = true,
}: {
  width?: "wide" | "medium" | "narrow";
  hero?: boolean;
}) {
  const rows = (
    <div className="flex flex-col gap-3 pt-2">
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
  if (hero) {
    return (
      <>
        <PageHero
          width={width}
          title={
            <>
              <span className="sr-only" role="status">
                Loading…
              </span>
              <span
                aria-hidden="true"
                className="block h-11 w-72 max-w-full animate-pulse rounded-xl bg-white/10"
              />
            </>
          }
          subtitle={
            <span
              aria-hidden="true"
              className="block h-5 w-96 max-w-full animate-pulse rounded-lg bg-white/8"
            />
          }
        />
        <Shell width={width}>{rows}</Shell>
      </>
    );
  }
  return (
    <Shell width={width}>
      <div className="flex flex-col gap-6">
        <span className="sr-only" role="status">
          Loading…
        </span>
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-5 w-96 max-w-full" />
        {rows}
      </div>
    </Shell>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-row border border-dashed border-line-strong bg-surface/60 px-6 py-12 text-center">
      <span className="flex size-12 items-center justify-center rounded-2xl bg-accent-subtle text-accent">
        {icon}
      </span>
      <span className="font-display text-lg font-bold text-ink">{title}</span>
      {children && <p className="max-w-[44ch] text-sm text-ink-2">{children}</p>}
      {action}
    </div>
  );
}

/**
 * Advisory integrity marker for recruiter screens. The wording is deliberate:
 * the signals come from browser-reported typing telemetry and can be wrong or
 * forged, so this says "worth a look", never "cheated".
 */
export function IntegrityBadge() {
  return (
    <span title="Typing telemetry suggests pasted or unusually fast answers. Advisory only — it never changes a score.">
      <Chip tone="warn">
        <AlertTriangle aria-hidden="true" className="size-3.5" />
        Integrity: worth a look
      </Chip>
    </span>
  );
}

/**
 * The passages a question was grounded in.
 *
 * Collapsed by default and expandable: a reviewer scanning a queue does not
 * want three paragraphs of reference material in the way, but the one who is
 * actually deciding a score needs to read it. Showing only a heading would
 * make the citation a claim rather than something checkable.
 */
export function CitedSources({
  sources,
  grounded,
  className = "",
}: {
  sources: CitedSource[];
  grounded: boolean;
  className?: string;
}) {
  if (!grounded || sources.length === 0) {
    // Said out loud rather than shown as an absence. An ungrounded question is
    // a normal outcome — the knowledge base does not cover everything — but a
    // reviewer should know the answer key came from the model, not a source.
    return (
      <p className={`text-xs text-ink-3 ${className}`}>
        Not grounded — the answer key came from the model, not from a cited source.
      </p>
    );
  }

  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      <span className="text-[11px] font-semibold tracking-[0.6px] text-ink-3 uppercase">
        Grounded in
      </span>
      {sources.map((source) => (
        <details
          key={source.chunk_id}
          className="rounded-control border border-line-soft bg-field px-3.5 py-2.5"
        >
          <summary className="cursor-pointer list-none text-[13px] font-medium text-ink marker:content-none">
            <span className="text-accent">{source.heading_path}</span>
            {source.url && (
              <a
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="ml-2 text-xs font-normal text-ink-3 hover:text-accent"
                onClick={(event) => event.stopPropagation()}
              >
                source ↗
              </a>
            )}
          </summary>
          <p className="mt-2 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-2">
            {source.text}
          </p>
          {source.license && (
            /* Shown because some licences require attribution wherever the
               text appears; hand-written content leaves this empty. */
            <p className="mt-2 text-[11px] text-ink-3">
              {source.document_title} — {source.license}
            </p>
          )}
        </details>
      ))}
    </div>
  );
}
