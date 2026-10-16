"use client";

/**
 * Every animation in the app goes through this file. Keeping them here means
 * one timing language (the design's soft ease-out) and one switch for people
 * who ask their OS for reduced motion — `MotionConfig reducedMotion="user"`
 * turns every transform below into an instant change for them.
 *
 * This is the client boundary for motion: `ui.tsx` stays importable from
 * server components and pulls the animated pieces in from here.
 */

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  animate,
  MotionConfig,
  motion,
  useInView,
  useReducedMotion,
  type Variants,
} from "motion/react";

export const EASE = [0.2, 0.8, 0.2, 1] as const;

export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user" transition={{ duration: 0.45, ease: EASE }}>
      {children}
    </MotionConfig>
  );
}

/** Rises a few pixels into place. The default entrance for a page section. */
export function FadeIn({
  children,
  delay = 0,
  y = 12,
  className,
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: EASE, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

/**
 * Like `FadeIn`, but waits until it scrolls into view — for the long public
 * landing page, where most sections start below the fold.
 */
export function Reveal({
  children,
  delay = 0,
  y = 24,
  className,
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  className?: string;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.7, ease: EASE, delay }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

const STAGGER: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
};

const STAGGER_ITEM: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: EASE } },
};

/** A list whose children (each a `StaggerItem`) arrive one after another. */
export function Stagger({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "ul" | "ol";
}) {
  const Component = motion[as];
  return (
    <Component variants={STAGGER} initial="hidden" animate="show" className={className}>
      {children}
    </Component>
  );
}

export function StaggerItem({
  children,
  className,
  as = "div",
}: {
  children: ReactNode;
  className?: string;
  as?: "div" | "li";
}) {
  const Component = motion[as];
  return (
    <Component variants={STAGGER_ITEM} className={className}>
      {children}
    </Component>
  );
}

/**
 * The filled part of a bar. The width is set as a plain style — so it is right
 * before, during and without animation — and the grow-in is a transform on top.
 */
export function BarFill({
  pct,
  className,
  delay = 0,
}: {
  pct: number;
  className?: string;
  delay?: number;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true });
  return (
    <motion.div
      ref={ref}
      className={className}
      style={{ width: `${pct}%`, transformOrigin: "left center" }}
      initial={{ scaleX: 0 }}
      animate={{ scaleX: inView ? 1 : 0 }}
      transition={{ duration: 0.9, ease: EASE, delay }}
    />
  );
}

/** Counts from 0 to `value` once it scrolls into view. */
export function CountUp({
  value,
  duration = 1.1,
  className,
}: {
  value: number;
  duration?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(0);

  useEffect(() => {
    // Reduced motion renders `value` directly below; nothing to animate.
    if (!inView || reduce) return;
    const controls = animate(0, value, {
      duration,
      ease: EASE,
      onUpdate: (v) => setShown(Math.round(v)),
    });
    return () => controls.stop();
  }, [inView, value, duration, reduce]);

  return (
    <span ref={ref} className={className}>
      {(reduce ? value : shown).toLocaleString()}
    </span>
  );
}

/**
 * The overall-score ring from the report hero: a track and an arc that sweeps
 * to `pct`, with the number counting up in the middle.
 */
export function ScoreRing({
  pct,
  size = 176,
  stroke = 16,
}: {
  pct: number;
  size?: number;
  stroke?: number;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(Math.max(pct, 0), 100);

  return (
    <div
      className="relative flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Overall score ${clamped} out of 100`}
    >
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-brand-ring)"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-glow)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: circumference * (1 - clamped / 100) }}
          transition={{ duration: 1.3, ease: EASE, delay: 0.15 }}
          style={{ filter: "drop-shadow(0 0 10px rgba(43,179,166,0.45))" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <CountUp
          value={clamped}
          className="tabular font-display text-[60px] leading-none font-bold"
        />
        <span className="text-sm text-ink-on-dark">out of 100</span>
      </div>
    </div>
  );
}

/**
 * A compact score ring for list rows: the arc draws in when the row scrolls
 * into view, the number sits in the middle. It names the score for screen
 * readers; the caller shows the visible "/100".
 */
export function MiniScoreRing({ pct, size = 54 }: { pct: number; size?: number }) {
  const ref = useRef<SVGSVGElement>(null);
  const inView = useInView(ref, { once: true });
  const stroke = 5;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.min(Math.max(pct, 0), 100);
  return (
    <div
      className="relative flex shrink-0 items-center justify-center"
      style={{ width: size, height: size }}
      role="img"
      aria-label={`Score ${clamped} out of 100`}
    >
      <svg ref={ref} width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-track)"
          strokeWidth={stroke}
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{
            strokeDashoffset: inView ? circumference * (1 - clamped / 100) : circumference,
          }}
          transition={{ duration: 1.1, ease: EASE, delay: 0.1 }}
        />
      </svg>
      <span className="tabular absolute font-display text-[17px] font-bold text-ink">
        {clamped}
      </span>
    </div>
  );
}

/** A soft pulsing dot for anything still in flight. */
export function PulseDot({ className = "bg-current" }: { className?: string }) {
  return (
    <span className="relative flex size-2">
      <motion.span
        className={`absolute inline-flex size-full rounded-full opacity-60 ${className}`}
        animate={{ scale: [1, 2.2], opacity: [0.6, 0] }}
        transition={{ duration: 1.4, repeat: Infinity, ease: "easeOut" }}
      />
      <span className={`relative inline-flex size-2 rounded-full ${className}`} />
    </span>
  );
}
