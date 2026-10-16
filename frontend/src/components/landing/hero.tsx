"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  AnimatePresence,
  motion,
  useMotionTemplate,
  useMotionValue,
  useSpring,
  useTransform,
  type MotionValue,
  type Variants,
} from "motion/react";
import { ArrowDown, Check, FileText, Mic, ShieldCheck, Upload } from "lucide-react";
import { RESUME_EXTENSIONS, resumeProblem } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import { EASE, PulseDot } from "@/components/motion";

const LINE_ONE = ["Interviews", "that", "grade", "fairly,"];
const LINE_TWO = ["and", "show", "their", "work."];

const HEADLINE: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.25 } },
};

const WORD: Variants = {
  hidden: { opacity: 0, y: "0.4em", filter: "blur(10px)" },
  show: { opacity: 1, y: 0, filter: "blur(0px)", transition: { duration: 0.8, ease: EASE } },
};

/**
 * The landing hero. Pointer position drives three things: a soft spotlight
 * that follows the cursor, a slight 3D tilt on the upload card, and parallax
 * on the preview cards around it — each layer at its own depth. All of it is
 * springs on motion values, so moving the mouse never re-renders React.
 */
export function Hero({ signedIn, onStart }: { signedIn: boolean; onStart: (file?: File) => void }) {
  // Pointer in pixels, for the spotlight, and normalised to -0.5..0.5 for tilt.
  const px = useMotionValue(-1000);
  const py = useMotionValue(-1000);
  const nx = useMotionValue(0);
  const ny = useMotionValue(0);
  const sx = useSpring(nx, { stiffness: 120, damping: 20, mass: 0.6 });
  const sy = useSpring(ny, { stiffness: 120, damping: 20, mass: 0.6 });
  const spotlight = useMotionTemplate`radial-gradient(640px circle at ${px}px ${py}px, rgba(43,179,166,0.16), transparent 65%)`;

  return (
    <section
      onPointerMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        px.set(e.clientX - r.left);
        py.set(e.clientY - r.top);
        nx.set((e.clientX - r.left) / r.width - 0.5);
        ny.set((e.clientY - r.top) / r.height - 0.5);
      }}
      onPointerLeave={() => {
        nx.set(0);
        ny.set(0);
      }}
      className="surface-hero relative isolate overflow-hidden pt-33 pb-24 sm:pt-37.5 sm:pb-32"
    >
      <Backdrop spotlight={spotlight} />

      <div className="relative mx-auto grid w-full max-w-280 items-center gap-16 px-4 sm:px-6 lg:grid-cols-[1.08fr_1fr] lg:gap-10">
        <div className="flex flex-col items-start gap-7">
          <motion.span
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EASE, delay: 0.15 }}
            className="inline-flex items-center gap-2.5 rounded-full border border-white/15 bg-white/6 px-3.5 py-1.5 text-[13px] font-medium text-ink-on-dark backdrop-blur-sm"
          >
            <PulseDot className="bg-glow" />
            Resume-driven skills interviews
          </motion.span>

          <motion.h1
            variants={HEADLINE}
            initial="hidden"
            animate="show"
            className="font-display text-[44px] leading-[1.02] font-bold tracking-[-0.03em] sm:text-[60px] lg:text-[68px]"
          >
            {LINE_ONE.map((word) => (
              <span key={word}>
                <motion.span variants={WORD} className="inline-block">
                  {word}
                </motion.span>{" "}
              </span>
            ))}
            <br className="hidden sm:block" />
            {LINE_TWO.map((word) => (
              <span key={word}>
                <motion.span
                  variants={WORD}
                  className="inline-block bg-linear-to-r from-[#9ff0e6] via-[#5fd3c6] to-glow bg-clip-text text-transparent"
                >
                  {word}
                </motion.span>{" "}
              </span>
            ))}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE, delay: 0.75 }}
            className="max-w-130 text-[18px] leading-relaxed text-ink-on-dark"
          >
            Upload your resume. We write questions on the skills you actually list, grade every
            answer two independent ways, and hand anything they disagree on to a person.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: EASE, delay: 0.9 }}
            className="flex flex-wrap items-center gap-3"
          >
            <button
              type="button"
              onClick={() => onStart()}
              className="group inline-flex min-h-13 cursor-pointer items-center gap-2 rounded-full bg-white px-7 text-[15px] font-semibold text-brand shadow-[0_16px_40px_-16px_rgba(0,0,0,0.6)] transition-[transform,box-shadow,background] duration-250 ease-out-soft hover:-translate-y-0.5 hover:bg-accent-soft hover:shadow-[0_20px_44px_-14px_rgba(43,179,166,0.55)] active:translate-y-0"
            >
              <Upload
                aria-hidden="true"
                className="size-4.5 transition-transform duration-250 group-hover:-translate-y-0.5"
              />
              Upload your resume
            </button>
            <a
              href="#how"
              className="group inline-flex min-h-13 items-center gap-2 rounded-full border border-white/20 px-6 text-[15px] font-semibold text-white transition-[background,border-color] duration-250 hover:border-white/40 hover:bg-white/8"
            >
              See how it works
              <ArrowDown
                aria-hidden="true"
                className="size-4 transition-transform duration-250 group-hover:translate-y-0.5"
              />
            </a>
          </motion.div>

          <motion.ul
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 1.1 }}
            className="flex flex-wrap gap-x-6 gap-y-2 text-sm text-ink-on-dark"
          >
            {[
              { icon: Check, text: "Graded twice" },
              { icon: Mic, text: "Type or speak answers" },
              { icon: ShieldCheck, text: "Reviewed by a person" },
            ].map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-center gap-2">
                <Icon aria-hidden="true" className="size-4 text-glow" />
                {text}
              </li>
            ))}
          </motion.ul>
        </div>

        <HeroVisual sx={sx} sy={sy} signedIn={signedIn} onFile={onStart} />
      </div>
    </section>
  );
}

/** Grid, drifting glows and the cursor spotlight — all decoration. */
function Backdrop({ spotlight }: { spotlight: MotionValue<string> }) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
      <div
        className="absolute inset-0 opacity-60"
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)",
          backgroundSize: "56px 56px",
          maskImage: "radial-gradient(ellipse 80% 70% at 60% 40%, black 30%, transparent 80%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 80% 70% at 60% 40%, black 30%, transparent 80%)",
        }}
      />
      <motion.span
        className="absolute -top-40 right-[-10%] size-140 rounded-full bg-glow/25 blur-3xl"
        animate={{ x: [0, -60, 0], y: [0, 40, 0] }}
        transition={{ duration: 18, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.span
        className="absolute -bottom-56 -left-32 size-120 rounded-full bg-accent/35 blur-3xl"
        animate={{ x: [0, 50, 0], y: [0, -30, 0] }}
        transition={{ duration: 20, repeat: Infinity, ease: "easeInOut" }}
      />
      <motion.div className="absolute inset-0" style={{ background: spotlight }} />
      {/* A hairline where the hero meets the page, lit in the middle. */}
      <div className="absolute inset-x-0 bottom-0 h-px bg-linear-to-r from-transparent via-glow/50 to-transparent" />
    </div>
  );
}

// --- The upload card and the cards floating around it ----------------------

function HeroVisual({
  sx,
  sy,
  signedIn,
  onFile,
}: {
  sx: MotionValue<number>;
  sy: MotionValue<number>;
  signedIn: boolean;
  onFile: (file: File) => void;
}) {
  const rotateX = useTransform(sy, (v) => v * -9);
  const rotateY = useTransform(sx, (v) => v * 11);

  return (
    <motion.div
      initial={{ opacity: 0, y: 40, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 1, ease: EASE, delay: 0.35 }}
      className="relative mx-auto w-full max-w-110 perspective-[1400px]"
    >
      <motion.div style={{ rotateX, rotateY, transformStyle: "preserve-3d" }}>
        <ResumeDrop signedIn={signedIn} onFile={onFile} />
      </motion.div>

      {/* Previews of what comes next. Decorative, and too crowded on a phone. */}
      <div aria-hidden="true" className="hidden sm:block">
        <Floater sx={sx} sy={sy} depth={30} bob={7} delay={0.9} className="-top-44 -left-24">
          <ThoughtCloud />
        </Floater>
        <Floater sx={sx} sy={sy} depth={16} bob={5} delay={1.25} className="-top-12 -right-5">
          <QuestionPebble />
        </Floater>
        <Floater sx={sx} sy={sy} depth={-24} bob={9} delay={1.1} className="-right-20 -bottom-30">
          <ScoreMedallion />
        </Floater>
        <Sparkle className="-top-40 left-62 size-4" delay={0.2} />
        <Sparkle className="right-34 -bottom-12 size-3" delay={1.4} />
      </div>
    </motion.div>
  );
}

/** Parallax with the pointer plus a slow idle float; the child brings its own shape. */
function Floater({
  sx,
  sy,
  depth,
  bob,
  delay,
  className,
  children,
}: {
  sx: MotionValue<number>;
  sy: MotionValue<number>;
  /** How far it drifts with the pointer; negative moves against it. */
  depth: number;
  /** Idle float amplitude, in pixels. */
  bob: number;
  delay: number;
  className: string;
  children: ReactNode;
}) {
  const x = useTransform(sx, (v) => v * depth);
  const y = useTransform(sy, (v) => v * depth);
  return (
    <motion.div
      style={{ x, y }}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 140, damping: 16, delay }}
      className={`absolute z-10 ${className}`}
    >
      <motion.div
        animate={{ y: [0, -bob, 0] }}
        transition={{ duration: 5 + bob / 3, repeat: Infinity, ease: "easeInOut", delay }}
      >
        {children}
      </motion.div>
    </motion.div>
  );
}

// A cloud drawn from five round bumps over a flat base, in a 280×160 box. The
// same path clips the frosted fill and draws the outline, so the two line up.
const CLOUD =
  "M 50 150 A 38 38 0 0 1 30 82 A 44 44 0 0 1 98 42 A 52 52 0 0 1 188 36 " +
  "A 42 42 0 0 1 252 86 A 36 36 0 0 1 232 150 Z";

const PREVIEW_SKILLS = [
  { name: "Python", value: 0.94 },
  { name: "FastAPI", value: 0.86 },
  { name: "PostgreSQL", value: 0.72 },
];

/** "Skills we found" as a thought: a cloud, with bubbles trailing to the card. */
function ThoughtCloud() {
  return (
    <div className="relative h-52 w-70">
      {/* A soft shadow under the cloud, since a clipped element can't cast one. */}
      <span className="absolute inset-x-8 top-24 h-20 rounded-full bg-black/40 blur-2xl" />
      <motion.div
        animate={{ scale: [1, 1.025, 1] }}
        transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
        className="absolute inset-x-0 top-0 h-40"
      >
        <div
          className="absolute inset-0 bg-[#0d3a41]/75 backdrop-blur-xl"
          style={{ clipPath: `path("${CLOUD}")` }}
        />
        <svg viewBox="0 0 280 160" className="absolute inset-0 size-full overflow-visible">
          <defs>
            <linearGradient id="cloud-sheen" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgba(159,240,230,0.16)" />
              <stop offset="100%" stopColor="rgba(159,240,230,0.02)" />
            </linearGradient>
          </defs>
          <path
            d={CLOUD}
            fill="url(#cloud-sheen)"
            stroke="rgba(255,255,255,0.2)"
            strokeWidth="1.2"
          />
        </svg>
        <div className="absolute inset-x-6 top-13 flex flex-col items-center gap-2">
          <span className="text-[10px] font-semibold tracking-[0.14em] text-[#9ff0e6] uppercase">
            Skills we found
          </span>
          <div className="flex flex-wrap justify-center gap-1">
            {PREVIEW_SKILLS.map((skill, i) => (
              <motion.span
                key={skill.name}
                initial={{ opacity: 0, scale: 0.6, y: 6 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                transition={{
                  type: "spring",
                  stiffness: 380,
                  damping: 18,
                  delay: 1.4 + i * 0.18,
                }}
                className="inline-flex items-center gap-1 rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-medium text-white ring-1 ring-white/10"
              >
                <span
                  className="size-1.5 rounded-full bg-glow"
                  style={{ opacity: 0.4 + skill.value * 0.6 }}
                />
                {skill.name}
                <span className="tabular text-ink-on-dark">{skill.value.toFixed(2)}</span>
              </motion.span>
            ))}
          </div>
        </div>
      </motion.div>

      {/* The thought trail, drifting down toward the upload card. */}
      {[
        { className: "left-55 top-40 size-4.5", delay: 0 },
        { className: "left-62 top-46 size-2.5", delay: 0.35 },
      ].map((bubble) => (
        <motion.span
          key={bubble.className}
          animate={{ scale: [1, 1.18, 1], opacity: [0.75, 1, 0.75] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut", delay: bubble.delay }}
          className={`absolute rounded-full border border-white/20 bg-[#0d3a41]/80 backdrop-blur-md ${bubble.className}`}
        />
      ))}
    </div>
  );
}

/** The live question, as a pebble whose outline slowly breathes. */
function QuestionPebble() {
  return (
    <motion.div
      animate={{
        borderRadius: [
          "46% 54% 52% 48% / 58% 46% 54% 42%",
          "56% 44% 46% 54% / 44% 58% 42% 56%",
          "46% 54% 52% 48% / 58% 46% 54% 42%",
        ],
      }}
      transition={{ duration: 7, repeat: Infinity, ease: "easeInOut" }}
      className="border border-white/18 bg-[#0d3a41]/75 px-5 py-3.5 shadow-[0_20px_40px_-20px_rgba(0,0,0,0.7)] backdrop-blur-xl"
    >
      <span className="flex items-center gap-2 text-[13px] font-medium whitespace-nowrap text-white">
        <PulseDot className="bg-glow" />
        Question 3 of 8 · 12 min left
      </span>
    </motion.div>
  );
}

/** The score as a round medal: a lit rim that slowly turns, the arc, a ribbon. */
function ScoreMedallion() {
  const size = 132;
  const stroke = 7;
  const r = (size - stroke) / 2 - 10;
  const c = 2 * Math.PI * r;
  const rim =
    "radial-gradient(farthest-side, transparent calc(100% - 2px), black calc(100% - 2px))";
  return (
    <div className="relative flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size }}>
        {/* A comet of light running round the rim. */}
        <motion.span
          animate={{ rotate: 360 }}
          transition={{ duration: 9, repeat: Infinity, ease: "linear" }}
          className="absolute -inset-1 rounded-full"
          style={{
            background:
              "conic-gradient(from 0deg, transparent 0deg, rgba(159,240,230,0.9) 70deg, transparent 140deg)",
            mask: rim,
            WebkitMask: rim,
          }}
        />
        <div className="absolute inset-0 rounded-full border border-white/15 bg-[#0d3a41]/80 shadow-[0_28px_56px_-24px_rgba(0,0,0,0.75)] backdrop-blur-xl" />
        <svg width={size} height={size} className="absolute inset-0 -rotate-90">
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="rgba(255,255,255,0.1)"
            strokeWidth={stroke}
          />
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke="var(--color-glow)"
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            animate={{ strokeDashoffset: c * (1 - 0.82) }}
            transition={{ duration: 1.4, ease: EASE, delay: 1.5 }}
            style={{ filter: "drop-shadow(0 0 6px rgba(43,179,166,0.6))" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="tabular font-display text-[32px] leading-none font-bold text-white">
            82
          </span>
          <span className="text-[11px] text-ink-on-dark">out of 100</span>
        </div>
      </div>
      <span className="relative -mt-3 inline-flex items-center gap-1 rounded-full bg-glow px-3 py-1 text-xs font-semibold text-brand shadow-[0_8px_20px_-8px_rgba(43,179,166,0.9)]">
        <Check aria-hidden="true" className="size-3.5" />
        Graders agree
      </span>
    </div>
  );
}

/** A four-pointed twinkle. */
function Sparkle({ className, delay }: { className: string; delay: number }) {
  return (
    <motion.svg
      viewBox="0 0 24 24"
      animate={{ scale: [0.6, 1, 0.6], opacity: [0.35, 1, 0.35], rotate: [0, 45, 0] }}
      transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut", delay }}
      className={`absolute text-[#9ff0e6] ${className}`}
    >
      <path
        d="M12 0c.6 6.6 5.4 11.4 12 12-6.6.6-11.4 5.4-12 12-.6-6.6-5.4-11.4-12-12C6.6 11.4 11.4 6.6 12 0Z"
        fill="currentColor"
      />
    </motion.svg>
  );
}

/**
 * A real drop zone: the file is checked here, then held in memory while the
 * visitor signs in, and pre-selected on the interview page when they arrive.
 * The short pause on the success state is there so the hand-off reads as
 * "got it" rather than as the page jumping away.
 */
function ResumeDrop({ signedIn, onFile }: { signedIn: boolean; onFile: (file: File) => void }) {
  const [dragging, setDragging] = useState(false);
  const [picked, setPicked] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  // The pending hand-off, cancelled if the visitor leaves before it fires —
  // otherwise it would yank them to sign-in from wherever they went next.
  const handOff = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(handOff.current), []);

  function pick(candidate: File | undefined) {
    if (!candidate || picked) return;
    const problem = resumeProblem(candidate);
    setError(problem);
    if (problem) return;
    setPicked(candidate);
    handOff.current = window.setTimeout(() => onFile(candidate), 1100);
  }

  return (
    <div className="relative rounded-[28px] border border-white/15 bg-white/7 p-3 shadow-[0_40px_80px_-32px_rgba(0,0,0,0.75)] backdrop-blur-xl">
      {/* A slow sheen across the card edge. */}
      <motion.span
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 rounded-[28px] bg-linear-to-r from-transparent via-white/7 to-transparent"
        initial={{ x: "-100%" }}
        animate={{ x: "100%" }}
        transition={{ duration: 3.2, repeat: Infinity, repeatDelay: 4, ease: "easeInOut" }}
      />
      <div className="relative flex flex-col gap-4 rounded-card bg-[#0b2f35]/60 p-6">
        <div className="flex items-center justify-between">
          <span className="text-[15px] font-semibold text-white">Start with your resume</span>
          <FileText aria-hidden="true" className="size-4.5 text-ink-on-dark" />
        </div>

        <label
          onDragOver={(e) => {
            e.preventDefault(); // without this the browser opens the file instead
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            pick(e.dataTransfer.files[0]);
          }}
          className={`group relative flex min-h-55 cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-row border-[1.5px] border-dashed px-5 py-8 text-center transition-[background,border-color,transform] duration-250 ease-out-soft ${
            dragging
              ? "scale-[1.02] border-glow bg-glow/15"
              : picked
                ? "border-glow/70 bg-glow/10"
                : "border-white/25 bg-white/3 hover:border-glow/70 hover:bg-white/6"
          }`}
        >
          <input
            type="file"
            aria-label="Choose your resume file"
            accept={RESUME_EXTENSIONS.join(",")}
            className="sr-only"
            disabled={picked !== null}
            onChange={(e) => {
              pick(e.target.files?.[0]);
              e.target.value = ""; // choosing the same file again should still fire
            }}
          />

          <AnimatePresence mode="wait" initial={false}>
            {picked ? (
              <motion.div
                key="picked"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.4, ease: EASE }}
                className="flex flex-col items-center gap-3"
                role="status"
              >
                <span className="flex size-14 items-center justify-center rounded-full bg-glow text-brand shadow-[0_0_0_8px_rgba(43,179,166,0.18)]">
                  <svg viewBox="0 0 24 24" className="size-7" fill="none" aria-hidden="true">
                    <motion.path
                      d="M5 12.5l4.5 4.5L19 7.5"
                      stroke="currentColor"
                      strokeWidth={2.6}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      initial={{ pathLength: 0 }}
                      animate={{ pathLength: 1 }}
                      transition={{ duration: 0.45, ease: EASE, delay: 0.15 }}
                    />
                  </svg>
                </span>
                <span className="max-w-65 truncate font-semibold text-white">{picked.name}</span>
                <span className="text-[13px] text-ink-on-dark">
                  {formatBytes(picked.size)} ·{" "}
                  {signedIn ? "opening your interviews…" : "sign in to continue…"}
                </span>
              </motion.div>
            ) : (
              <motion.div
                key="empty"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ duration: 0.25 }}
                className="flex flex-col items-center gap-3"
              >
                <motion.span
                  animate={dragging ? { y: -6, scale: 1.08 } : { y: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 400, damping: 22 }}
                  className="flex size-14 items-center justify-center rounded-2xl bg-white/10 text-[#9ff0e6] ring-1 ring-white/15 transition-colors duration-250 group-hover:bg-glow/20"
                >
                  {dragging ? (
                    <FileText aria-hidden="true" className="size-6" />
                  ) : (
                    <Upload aria-hidden="true" className="size-6" />
                  )}
                </motion.span>
                <span className="font-semibold text-white">
                  {dragging ? (
                    "Drop it here"
                  ) : (
                    <>
                      Drop your resume, or{" "}
                      <span className="text-[#9ff0e6] underline underline-offset-4">browse</span>
                    </>
                  )}
                </span>
                <span className="text-[13px] text-ink-on-dark">PDF, DOCX or TXT, up to 2 MB</span>
              </motion.div>
            )}
          </AnimatePresence>
        </label>

        <AnimatePresence initial={false}>
          {error && (
            <motion.p
              role="alert"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="text-[13px] font-medium text-[#ffb59a]"
            >
              {error}
            </motion.p>
          )}
        </AnimatePresence>

        <p className="text-center text-xs text-ink-on-dark">
          {signedIn
            ? "We'll pick it up on your interviews page."
            : "We hold onto it while you sign in or create an account."}
        </p>
      </div>
    </div>
  );
}
