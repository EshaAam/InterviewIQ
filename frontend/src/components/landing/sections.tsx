"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import {
  AnimatePresence,
  motion,
  useInView,
  useMotionTemplate,
  useMotionValue,
  useScroll,
  useSpring,
} from "motion/react";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  Briefcase,
  CircleCheck,
  FileDown,
  FileSearch,
  Gauge,
  ListChecks,
  Mic,
  RefreshCw,
  Scale,
  ShieldCheck,
  SlidersHorizontal,
  Timer,
  Upload,
  UserCheck,
} from "lucide-react";
import type { User } from "@/lib/auth";
import { homeFor, loginHref } from "@/lib/use-user";
import { EASE, Reveal, Stagger, StaggerItem } from "@/components/motion";

const CONTAINER = "mx-auto w-full max-w-280 px-4 sm:px-6";

function SectionHeading({
  eyebrow,
  title,
  children,
  tone = "light",
  align = "center",
}: {
  eyebrow: string;
  title: ReactNode;
  children?: ReactNode;
  tone?: "dark" | "light";
  align?: "center" | "left";
}) {
  const centered = align === "center";
  return (
    <Reveal
      className={`flex flex-col gap-4 ${centered ? "mx-auto max-w-170 items-center text-center" : "items-start"}`}
    >
      <span
        className={`text-[13px] font-semibold tracking-[0.12em] uppercase ${
          tone === "dark" ? "text-accent" : "text-[#9ff0e6]"
        }`}
      >
        {eyebrow}
      </span>
      <h2
        className={`font-display text-[34px] leading-[1.08] font-bold tracking-tight sm:text-[44px] ${
          tone === "dark" ? "text-ink" : "text-white"
        }`}
      >
        {title}
      </h2>
      {children && (
        <p
          className={`text-[17px] leading-relaxed ${tone === "dark" ? "text-ink-2" : "text-ink-on-dark"}`}
        >
          {children}
        </p>
      )}
    </Reveal>
  );
}

// --- Topics marquee --------------------------------------------------------

const TOPICS = [
  "Python",
  "FastAPI",
  "PostgreSQL",
  "React",
  "TypeScript",
  "Kubernetes",
  "Docker",
  "Redis",
  "System design",
  "AWS",
  "Go",
  "Node.js",
  "GraphQL",
  "Kafka",
  "Terraform",
  "Machine learning",
  "Django",
  "Rust",
];

export function TopicMarquee() {
  return (
    <section
      aria-label="Example interview topics"
      className="surface-deeper border-y border-white/8 py-9"
    >
      <p className="mb-6 text-center text-sm text-ink-on-dark">
        Questions follow the stack on <span className="font-semibold text-white">your</span> resume,
        for example
      </p>
      <div className="relative overflow-hidden mask-[linear-gradient(90deg,transparent,black_12%,black_88%,transparent)]">
        {/* Two copies back to back, slid by exactly one copy's width, loop
            seamlessly. Spacing is padding, not `gap`, so the halves match. */}
        <motion.ul
          className="flex w-max"
          animate={{ x: ["0%", "-50%"] }}
          transition={{ duration: 45, ease: "linear", repeat: Infinity }}
        >
          {[...TOPICS, ...TOPICS].map((topic, i) => (
            <li key={i} aria-hidden={i >= TOPICS.length || undefined} className="pr-3">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/4 px-4 py-2 text-sm font-medium whitespace-nowrap text-ink-on-dark backdrop-blur-sm">
                <span className="size-1.5 rounded-full bg-glow" />
                {topic}
              </span>
            </li>
          ))}
        </motion.ul>
      </div>
    </section>
  );
}

// --- How it works ----------------------------------------------------------

const STEPS = [
  {
    icon: Upload,
    title: "Upload your resume",
    body: "A PDF, DOCX or TXT up to 2 MB, or paste the text straight in.",
  },
  {
    icon: FileSearch,
    title: "We pick out your skills",
    body: "Each with a confidence score for how clearly your resume shows it. Questions follow these topics.",
  },
  {
    icon: Timer,
    title: "Answer against the clock",
    body: "Type or speak your answers. The clock starts only when you press Start.",
  },
  {
    icon: Gauge,
    title: "Get a report that shows its work",
    body: "Scores by topic, the sources each question drew on, and a PDF to keep.",
  },
];

export function HowItWorks() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 85%", "end 55%"] });
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 30 });

  return (
    <section id="how" className="surface-deep scroll-mt-24 py-24 sm:py-32">
      <div className={CONTAINER}>
        <SectionHeading eyebrow="How it works" title="From resume to report in four steps.">
          No generic question bank. Everything you&apos;re asked comes from what you wrote.
        </SectionHeading>

        <div ref={ref} className="relative mt-16">
          {/* The line that connects the steps fills in as you scroll past them. */}
          <div
            aria-hidden="true"
            className="absolute top-7 right-[12.5%] left-[12.5%] hidden h-0.5 overflow-hidden rounded-full bg-white/10 md:block"
          >
            <motion.div
              className="h-full origin-left bg-linear-to-r from-accent to-glow"
              style={{ scaleX: progress }}
            />
          </div>

          <ol className="relative grid gap-5 md:grid-cols-4">
            {STEPS.map(({ icon: Icon, title, body }, i) => (
              <motion.li
                key={title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ duration: 0.7, ease: EASE, delay: i * 0.1 }}
                className="group flex h-full flex-col items-center gap-4 text-center"
              >
                <span className="relative flex size-14 items-center justify-center rounded-2xl border border-white/12 bg-white/5 text-[#9ff0e6] shadow-[0_12px_28px_-14px_rgba(0,0,0,0.6)] backdrop-blur-sm transition-[transform,box-shadow,border-color,background] duration-300 ease-out-soft group-hover:-translate-y-1 group-hover:border-glow/60 group-hover:bg-glow/15 group-hover:shadow-[0_18px_36px_-16px_rgba(43,179,166,0.45)]">
                  <Icon aria-hidden="true" className="size-6" />
                  <span className="tabular absolute -top-2 -right-2 flex size-6 items-center justify-center rounded-full bg-glow text-[11px] font-bold text-brand ring-4 ring-[#0b2e34]">
                    {i + 1}
                  </span>
                </span>
                <span className="text-[17px] font-semibold text-white">{title}</span>
                <span className="max-w-60 text-[15px] leading-relaxed text-ink-on-dark">
                  {body}
                </span>
              </motion.li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}

// --- Grading ---------------------------------------------------------------

const SCENARIOS = {
  agree: {
    label: "Graders agree",
    concept: 78,
    model: 81,
    regrade: null,
    tone: "ok" as const,
    verdict: "Score stands",
    detail: "The two passes landed close together, so the grade is used.",
  },
  disagree: {
    label: "Graders disagree",
    concept: 38,
    model: 86,
    regrade: 84,
    tone: "warn" as const,
    verdict: "Sent to a recruiter",
    detail: "Still far apart after the model grades again, so a person decides.",
  },
};
type ScenarioKey = keyof typeof SCENARIOS;

export function Grading() {
  return (
    <section id="grading" className="surface-deep scroll-mt-24 pb-24 sm:pb-32">
      <div className={CONTAINER}>
        <Reveal>
          <div className="surface-hero relative isolate overflow-hidden rounded-4xl px-6 py-12 ring-1 ring-white/10 sm:px-12 sm:py-16">
            <motion.span
              aria-hidden="true"
              className="pointer-events-none absolute -top-40 -left-24 -z-10 size-115 rounded-full bg-glow/20 blur-3xl"
              animate={{ x: [0, 40, 0], y: [0, 30, 0] }}
              transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
            />
            <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.05fr]">
              <div className="flex flex-col gap-8">
                <SectionHeading
                  tone="light"
                  align="left"
                  eyebrow="Grading"
                  title="Every answer graded twice. A person settles the rest."
                >
                  A deterministic pass checks which expected concepts your answer covers. A model
                  grades it independently. If they land far apart, the model grades again, and if
                  they still disagree, a recruiter reads the answer instead of anything being
                  averaged.
                </SectionHeading>
                <Stagger as="ul" className="flex flex-col gap-3">
                  {[
                    {
                      icon: Scale,
                      text: "Anchored scores: the same answer gets the same check every time.",
                    },
                    {
                      icon: BookOpen,
                      text: "Questions can be grounded in cited reference material.",
                    },
                    {
                      icon: UserCheck,
                      text: "Scores are advisory until a person agrees with them.",
                    },
                  ].map(({ icon: Icon, text }) => (
                    <StaggerItem
                      as="li"
                      key={text}
                      className="flex items-start gap-3 text-[15px] text-ink-on-dark"
                    >
                      <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-glow/20 text-[#9ff0e6]">
                        <Icon aria-hidden="true" className="size-4" />
                      </span>
                      {text}
                    </StaggerItem>
                  ))}
                </Stagger>
              </div>
              <GradingDemo />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/**
 * A worked example of the two-pass policy. It flips between the two outcomes
 * on its own while on screen, until someone picks one — after that it stays
 * where they put it.
 */
function GradingDemo() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { amount: 0.5 });
  const [key, setKey] = useState<ScenarioKey>("agree");
  const [pinned, setPinned] = useState(false);
  const [hovering, setHovering] = useState(false);

  useEffect(() => {
    if (!inView || pinned || hovering) return;
    const id = window.setTimeout(() => setKey((k) => (k === "agree" ? "disagree" : "agree")), 5200);
    return () => window.clearTimeout(id);
  }, [inView, pinned, hovering, key]);

  const s = SCENARIOS[key];
  const gap = Math.abs(s.concept - s.model);

  return (
    <div
      ref={ref}
      onMouseEnter={() => setHovering(true)}
      onMouseLeave={() => setHovering(false)}
      className="rounded-3xl border border-white/12 bg-white/6 p-5 shadow-[0_32px_64px_-32px_rgba(0,0,0,0.7)] backdrop-blur-xl sm:p-6"
    >
      <div
        role="radiogroup"
        aria-label="Example outcome"
        className="grid grid-cols-2 gap-1 rounded-[14px] bg-black/20 p-1"
      >
        {(Object.keys(SCENARIOS) as ScenarioKey[]).map((k) => {
          const active = k === key;
          return (
            <button
              key={k}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => {
                setKey(k);
                setPinned(true);
              }}
              className={`relative min-h-10 cursor-pointer rounded-[10px] text-sm transition-colors duration-200 ${
                active
                  ? "font-semibold text-white"
                  : "font-medium text-ink-on-dark hover:text-white"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="grading-tab"
                  className="btn-glow absolute inset-0 rounded-[10px]"
                  transition={{ type: "spring", stiffness: 480, damping: 38 }}
                />
              )}
              <span className="relative">{SCENARIOS[k].label}</span>
            </button>
          );
        })}
      </div>

      <div className="mt-5 rounded-[14px] border border-white/10 bg-black/15 px-4 py-3.5">
        <span className="text-[11px] font-semibold tracking-[0.6px] text-ink-on-dark uppercase">
          Question · PostgreSQL
        </span>
        <p className="mt-1 text-[15px] text-white">
          How does MVCC let readers and writers work on the same rows at once?
        </p>
      </div>

      <div className="mt-5 flex flex-col gap-4">
        <GradeBar label="Concept coverage" sub="deterministic" value={s.concept} />
        <GradeBar label="Model grade" sub="independent" value={s.model} delay={0.12} />
      </div>

      <div className="mt-5 flex min-h-33 flex-col gap-2.5">
        <AnimatePresence mode="wait">
          <motion.div
            key={key}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35, ease: EASE }}
            className="flex flex-col gap-2.5"
          >
            <span className="tabular text-[13px] text-ink-on-dark">
              Gap: <span className="font-semibold text-white">{gap} points</span>
            </span>
            {s.regrade !== null && (
              <motion.span
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, ease: EASE, delay: 0.5 }}
                className="tabular flex items-center gap-2 text-[13px] text-ink-on-dark"
              >
                <RefreshCw aria-hidden="true" className="size-3.5 text-[#9ff0e6]" />
                Model grades again: {s.regrade}, still {Math.abs(s.concept - s.regrade)} apart
              </motion.span>
            )}
            <motion.div
              initial={{ opacity: 0, scale: 0.96 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.45, ease: EASE, delay: s.regrade !== null ? 0.95 : 0.45 }}
              className={`flex items-start gap-3 rounded-[14px] px-4 py-3 ${
                s.tone === "ok"
                  ? "bg-ok/35 ring-1 ring-[#4fd18f]/30"
                  : "bg-warn/35 ring-1 ring-[#ffb08a]/30"
              }`}
            >
              {s.tone === "ok" ? (
                <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-[#7fe8b0]" />
              ) : (
                <UserCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-[#ffc4a6]" />
              )}
              <span className="flex flex-col">
                <span className="font-semibold text-white">{s.verdict}</span>
                <span className="text-[13px] text-ink-on-dark">{s.detail}</span>
              </span>
            </motion.div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}

function GradeBar({
  label,
  sub,
  value,
  delay = 0,
}: {
  label: string;
  sub: string;
  value: number;
  delay?: number;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <span className="text-sm font-medium text-white">
          {label} <span className="text-xs font-normal text-ink-on-dark">· {sub}</span>
        </span>
        <motion.span
          key={value}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: EASE, delay }}
          className="tabular font-display text-[20px] leading-none font-bold text-white"
        >
          {value}
        </motion.span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/10">
        <motion.div
          className="h-full rounded-full bg-linear-to-r from-accent to-glow"
          initial={{ width: 0 }}
          animate={{ width: `${value}%` }}
          transition={{ type: "spring", stiffness: 70, damping: 16, delay }}
        />
      </div>
    </div>
  );
}

// --- Features --------------------------------------------------------------

const FEATURES = [
  {
    icon: FileSearch,
    title: "Questions from your own resume",
    body: "We pick out the skills you list and write questions on exactly those, not a generic bank.",
  },
  {
    icon: Mic,
    title: "Type or speak your answers",
    body: "Record an answer and fix the transcript before you submit. Spoken answers are graded exactly like typed ones.",
  },
  {
    icon: Briefcase,
    title: "Aim it at a specific role",
    body: "Paste a job description and the questions focus on what your resume doesn't already cover.",
  },
  {
    icon: BookOpen,
    title: "Sources you can check",
    body: "See the reference passages a question was grounded in, or a plain note when it wasn't.",
  },
  {
    icon: SlidersHorizontal,
    title: "Scores by topic",
    body: "See where you're strong and where to practise next, topic by topic, not one opaque number.",
  },
  {
    icon: FileDown,
    title: "A PDF to keep",
    body: "Download the full report and keep it with your notes, or share it.",
  },
];

export function Features() {
  return (
    <section className="surface-deeper border-y border-white/8 py-24 sm:py-32">
      <div className={CONTAINER}>
        <SectionHeading
          eyebrow="For candidates"
          title="Practice that tells you where you actually stand."
        >
          Built for being checked, not just trusted.
        </SectionHeading>
        <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }, i) => (
            <Reveal key={title} delay={(i % 3) * 0.08}>
              <SpotlightCard>
                <span className="flex size-11 items-center justify-center rounded-xl bg-glow/15 text-[#9ff0e6] ring-1 ring-glow/25 transition-transform duration-300 ease-out-soft group-hover:scale-110 group-hover:-rotate-6">
                  <Icon aria-hidden="true" className="size-5" />
                </span>
                <span className="mt-5 block text-[17px] font-semibold text-white">{title}</span>
                <span className="mt-1.5 block text-[15px] leading-relaxed text-ink-on-dark">
                  {body}
                </span>
              </SpotlightCard>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

/** A card with a soft teal glow that follows the pointer across it. */
function SpotlightCard({ children }: { children: ReactNode }) {
  const x = useMotionValue(-400);
  const y = useMotionValue(-400);
  const glow = useMotionTemplate`radial-gradient(320px circle at ${x}px ${y}px, rgba(43,179,166,0.2), transparent 70%)`;
  return (
    <div
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        x.set(e.clientX - r.left);
        y.set(e.clientY - r.top);
      }}
      className="group relative h-full overflow-hidden rounded-card border border-white/10 bg-white/4 p-6 backdrop-blur-sm transition-[transform,box-shadow,border-color,background] duration-300 ease-out-soft hover:-translate-y-1 hover:border-glow/40 hover:bg-white/6 hover:shadow-[0_24px_48px_-24px_rgba(0,0,0,0.6)]"
    >
      <motion.div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
        style={{ background: glow }}
      />
      <div className="relative">{children}</div>
    </div>
  );
}

// --- Recruiters ------------------------------------------------------------

const QUEUE = [
  { session: "7F3A", topic: "Kubernetes", concept: 29, model: 81 },
  { session: "C210", topic: "PostgreSQL", concept: 38, model: 86 },
  { session: "9B4E", topic: "System design", concept: 74, model: 31 },
];

export function Recruiters() {
  return (
    <section id="recruiters" className="surface-deep scroll-mt-24 py-24 sm:py-32">
      <div className={`${CONTAINER} grid items-center gap-14 lg:grid-cols-2`}>
        <div className="flex flex-col gap-8">
          <SectionHeading
            align="left"
            eyebrow="For recruiters"
            title="Read only the answers that need a person."
          >
            The review queue holds just the answers the two graders couldn&apos;t agree on.
            Everything else is scored, explained and ready to compare.
          </SectionHeading>
          <Stagger as="ul" className="flex flex-col gap-3.5">
            {[
              { icon: ListChecks, text: "A review queue of disagreements, not every answer" },
              { icon: Scale, text: "Set the final score yourself, with a note on why" },
              {
                icon: AlertTriangle,
                text: "Integrity signals flagged as worth a look, never as verdicts",
              },
              { icon: Gauge, text: "Per-session model costs, in a ledger you can audit" },
            ].map(({ icon: Icon, text }) => (
              <StaggerItem
                as="li"
                key={text}
                className="flex items-center gap-3 text-[15px] text-ink-on-dark"
              >
                <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-glow/15 text-[#9ff0e6]">
                  <Icon aria-hidden="true" className="size-4" />
                </span>
                {text}
              </StaggerItem>
            ))}
          </Stagger>
          <Reveal>
            <p className="text-sm text-ink-on-dark">
              Recruiter accounts are set up by your administrator.{" "}
              <Link
                href={loginHref()}
                className="font-semibold text-[#9ff0e6] underline-offset-4 hover:text-white hover:underline"
              >
                Sign in
              </Link>
            </p>
          </Reveal>
        </div>

        <Reveal delay={0.1}>
          <div
            aria-hidden="true"
            className="rounded-card border border-white/10 bg-white/4 p-5 shadow-[0_32px_64px_-32px_rgba(0,0,0,0.7)] backdrop-blur-sm sm:p-6"
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <span className="text-[15px] font-semibold text-white">Review queue</span>
              <span className="rounded-full px-2.5 py-1 text-xs font-semibold bg-[#9a4416]/30 text-[#ffc4a6] ring-1 ring-[#ffb08a]/25">
                3 waiting
              </span>
            </div>
            <Stagger className="mt-4 flex flex-col gap-2.5">
              {QUEUE.map((row) => (
                <StaggerItem key={row.session}>
                  <div className="group flex items-center gap-4 rounded-row border border-white/8 bg-white/3 px-4 py-3.5 transition-[transform,border-color,background] duration-250 ease-out-soft hover:translate-x-1 hover:border-glow/40 hover:bg-white/7">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <span className="text-sm font-semibold text-white">
                        Session {row.session} · {row.topic}
                      </span>
                      <span className="tabular text-[13px] text-ink-on-dark">
                        Concepts {row.concept} · Model {row.model}
                      </span>
                    </div>
                    <span className="tabular rounded-full px-2.5 py-1 text-xs font-semibold bg-[#9a4416]/30 text-[#ffc4a6] ring-1 ring-[#ffb08a]/25">
                      Δ {Math.abs(row.concept - row.model)}
                    </span>
                    <ArrowRight className="size-4 text-[#9ff0e6] transition-transform duration-250 group-hover:translate-x-0.5" />
                  </div>
                </StaggerItem>
              ))}
            </Stagger>
            <div className="mt-4 flex items-center gap-2 rounded-row bg-glow/10 px-4 py-3 text-[13px] text-ink-on-dark ring-1 ring-glow/20">
              <ShieldCheck className="size-4 shrink-0 text-[#9ff0e6]" />
              Overriding a score never erases what the graders said.
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

// --- Closing call to action and footer --------------------------------------

export function FinalCta({ user, onStart }: { user: User | null; onStart: () => void }) {
  return (
    <section className="surface-deep pb-24 sm:pb-32">
      <div className={CONTAINER}>
        <Reveal>
          <div className="surface-hero relative isolate overflow-hidden rounded-4xl px-6 py-16 ring-1 ring-white/10 text-center sm:px-12 sm:py-20">
            <motion.span
              aria-hidden="true"
              className="pointer-events-none absolute -right-24 -bottom-48 -z-10 size-120 rounded-full bg-glow/25 blur-3xl"
              animate={{ x: [0, -40, 0], y: [0, -20, 0] }}
              transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
            />
            <h2 className="mx-auto max-w-160 font-display text-[34px] leading-[1.08] font-bold tracking-tight sm:text-[48px]">
              Your next interview starts with your resume.
            </h2>
            <p className="mx-auto mt-4 max-w-130 text-[17px] text-ink-on-dark">
              Upload it, answer a handful of questions, and see where you stand by topic.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <motion.button
                type="button"
                onClick={onStart}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.98 }}
                transition={{ type: "spring", stiffness: 400, damping: 22 }}
                className="inline-flex min-h-13 cursor-pointer items-center gap-2 btn-glow rounded-full px-7 text-[15px] font-semibold transition-[background,box-shadow] duration-200"
              >
                <Upload aria-hidden="true" className="size-4.5" />
                Upload your resume
              </motion.button>
              <Link
                href={user ? homeFor(user) : loginHref()}
                className="inline-flex min-h-13 items-center rounded-full border border-white/20 px-6 text-[15px] font-semibold text-white transition-[background,border-color] duration-250 hover:border-white/40 hover:bg-white/8"
              >
                {user ? (user.role === "recruiter" ? "Review queue" : "My interviews") : "Sign in"}
              </Link>
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
