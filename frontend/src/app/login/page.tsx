"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ArrowLeft, FileCheck2, FileSearch, Scale, UserCheck } from "lucide-react";
import { ApiError, login, me, register } from "@/lib/api";
import { usePendingResume } from "@/lib/pending-resume";
import { destinationFor, useUser } from "@/lib/use-user";
import { Logo } from "@/components/brand";
import { EASE, Stagger, StaggerItem } from "@/components/motion";
import { Button, ErrorBanner, Field } from "@/components/ui";

const FEATURES = [
  {
    icon: FileSearch,
    title: "Questions from your own resume",
    body: "We pick out the skills you list and write questions on exactly those.",
  },
  {
    icon: Scale,
    title: "Every answer graded twice",
    body: "A rule-based check and a model check, compared before anything is trusted.",
  },
  {
    icon: UserCheck,
    title: "A person settles disagreements",
    body: "When the two grades disagree, a recruiter reads it instead of averaging.",
  },
];

/**
 * Where the visitor was headed before being asked to sign in. Read from the
 * URL at the moment it's needed rather than with `useSearchParams`, which
 * would force a Suspense boundary around the whole (otherwise static) page.
 */
function nextParam(): string | null {
  return new URLSearchParams(window.location.search).get("next");
}

export default function LoginPage() {
  const router = useRouter();
  // Someone who is already signed in has no business on this form.
  const { user } = useUser({ redirectTo: null });
  useEffect(() => {
    if (user) router.replace(destinationFor(user, nextParam()));
  }, [user, router]);
  // A resume picked on the landing page, waiting for the account to land in.
  const pendingFile = usePendingResume();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        await register(email, password);
      }
      await login(email, password);
      // Route on the account the backend says this is: a recruiter signs in on
      // this same form, and only the server knows which kind of account it is.
      router.replace(destinationFor(await me(), nextParam()));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not reach the server");
      setBusy(false);
    }
  }

  return (
    <main className="grid min-h-screen flex-1 lg:grid-cols-[1.05fr_1fr]">
      {/* Brand panel — decoration and pitch, so it is hidden from small screens. */}
      <section
        aria-hidden="true"
        className="surface-hero relative hidden flex-col justify-between overflow-hidden p-12 lg:flex"
      >
        <motion.span
          className="pointer-events-none absolute -top-32 -right-24 size-115 rounded-full bg-glow/25 blur-3xl"
          animate={{ x: [0, -40, 0], y: [0, 30, 0] }}
          transition={{ duration: 14, repeat: Infinity, ease: "easeInOut" }}
        />
        <motion.span
          className="pointer-events-none absolute -bottom-40 -left-20 size-95 rounded-full bg-accent/30 blur-3xl"
          animate={{ x: [0, 30, 0], y: [0, -24, 0] }}
          transition={{ duration: 16, repeat: Infinity, ease: "easeInOut" }}
        />

        <div className="relative">
          <Logo size="lg" tone="light" />
        </div>

        <div className="relative flex max-w-120 flex-col gap-8">
          <motion.h2
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: EASE }}
            className="font-display text-[44px] leading-[1.05] font-bold tracking-[-0.02em]"
          >
            Interviews that grade fairly, and show their work.
          </motion.h2>
          <Stagger className="flex flex-col gap-4">
            {FEATURES.map(({ icon: Icon, title, body }) => (
              <StaggerItem
                key={title}
                className="flex gap-4 rounded-2xl bg-white/6 p-4 ring-1 ring-white/10 backdrop-blur-sm transition-colors duration-250 hover:bg-white/10"
              >
                <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-glow/20 text-[#7fe0d6]">
                  <Icon className="size-5" />
                </span>
                <span className="flex flex-col gap-0.5">
                  <span className="font-semibold">{title}</span>
                  <span className="text-sm text-ink-on-dark">{body}</span>
                </span>
              </StaggerItem>
            ))}
          </Stagger>
        </div>

        <p className="relative text-sm text-ink-on-dark">
          Scores are advisory until a person agrees with them.
        </p>
      </section>

      <section className="relative flex items-center justify-center px-4 py-12 sm:px-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: EASE }}
          className="w-full max-w-105"
        >
          <form onSubmit={submit} className="flex flex-col gap-6">
            <span className="lg:hidden">
              <Logo />
            </span>

            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={mode}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.22, ease: EASE }}
                className="flex flex-col gap-2"
              >
                <h1 className="font-display text-[36px] leading-[1.1] font-bold tracking-[-0.02em]">
                  {mode === "signin" ? "Welcome back" : "Create your account"}
                </h1>
                <p className="text-[17px] text-ink-2">
                  {mode === "signin"
                    ? "Sign in to continue your interviews, or review candidates."
                    : "Upload a resume and take a skills interview written for you."}
                </p>
              </motion.div>
            </AnimatePresence>

            <Field
              label="Email"
              type="email"
              required
              autoComplete="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Field
              label="Password"
              type="password"
              required
              minLength={8}
              autoComplete={mode === "signin" ? "current-password" : "new-password"}
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              hint={mode === "register" ? "At least 8 characters." : undefined}
            />

            {mode === "register" && (
              <p className="text-[13px] text-ink-3">
                New accounts are candidate accounts. Recruiter access is set up by your
                administrator.
              </p>
            )}

            {pendingFile && (
              <motion.div
                initial={{ opacity: 0, scale: 0.97 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.35, ease: EASE, delay: 0.15 }}
                className="flex items-center gap-3 rounded-[14px] border border-accent-ring bg-accent-soft px-4 py-3"
              >
                <FileCheck2 aria-hidden="true" className="size-5 shrink-0 text-accent" />
                <span className="min-w-0 text-sm text-ink-2">
                  <span className="block truncate font-semibold text-ink">{pendingFile.name}</span>
                  Ready to upload as soon as you&apos;re signed in.
                </span>
              </motion.div>
            )}

            {error && <ErrorBanner message={error} />}

            <Button type="submit" size="lg" loading={busy} className="w-full">
              {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
            </Button>

            <button
              type="button"
              onClick={() => {
                setMode(mode === "signin" ? "register" : "signin");
                setError(null);
              }}
              className="cursor-pointer self-center text-sm font-medium text-accent underline-offset-4 hover:text-brand hover:underline"
            >
              {mode === "signin" ? "No account? Create one." : "Already have an account? Sign in."}
            </button>
          </form>
        </motion.div>

        {/* After the form in the DOM so Email stays the first Tab stop;
            pinned to the top corner visually. */}
        <Link
          href="/"
          className="group absolute top-5 left-4 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-ink-2 transition-colors duration-200 hover:bg-accent-hover hover:text-ink sm:left-8"
        >
          <ArrowLeft
            aria-hidden="true"
            className="size-4 transition-transform duration-250 group-hover:-translate-x-0.5"
          />
          Home
        </Link>
      </section>
    </main>
  );
}
