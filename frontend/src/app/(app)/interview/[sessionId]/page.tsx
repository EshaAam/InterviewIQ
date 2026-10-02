"use client";

import { use, useCallback, useEffect, useId, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import {
  Check,
  CircleCheckBig,
  ClipboardPaste,
  Hourglass,
  Info,
  ListChecks,
  Sparkles,
  Timer,
  TriangleAlert,
} from "lucide-react";
import {
  ApiError,
  describeError,
  finishSession,
  getSession,
  nextQuestion,
  startSession,
  submitAnswer,
  type Question,
  type Session,
  type SessionState,
} from "@/lib/api";
import { isAbort, pollUntil, PollTimeout } from "@/lib/poll";
import { EASE, FadeIn } from "@/components/motion";
import {
  Button,
  buttonClass,
  Card,
  Chip,
  ErrorBanner,
  FIELD_CLASS,
  Notice,
  PageLoading,
  Shell,
  Skeleton,
  StatusPill,
  Tag,
} from "@/components/ui";

/**
 * Server-authoritative deadline, rendered as mm:ss. Display only: it never
 * submits or locks anything. `passed` just tells the page it's worth asking
 * the server — which is the one that actually decides.
 */
function useCountdown(
  expiresAt: string | null,
): { label: string; passed: boolean; urgent: boolean } | null {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!expiresAt) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  if (!expiresAt) return null;
  const remaining = Math.max(0, new Date(expiresAt).getTime() - now);
  const minutes = Math.floor(remaining / 60000);
  const seconds = Math.floor((remaining % 60000) / 1000);
  return {
    label: `${minutes}:${String(seconds).padStart(2, "0")}`,
    passed: remaining === 0,
    urgent: remaining < 5 * 60_000,
  };
}

/**
 * The moments when this page waits on the server instead of the candidate.
 * Each one polls `GET /sessions/{id}` until the state leaves the waiting set.
 */
type WaitPhase = "preparing" | "grading" | "deadline";

const PREPARING: SessionState[] = ["CREATED", "PARSING", "GENERATING_QS"];

const WAITS: Record<WaitPhase, { settled: (s: Session) => boolean; timeoutMs: number }> = {
  // The worker is writing questions.
  preparing: { settled: (s) => !PREPARING.includes(s.state), timeoutMs: 3 * 60_000 },
  // The worker is grading and building the report.
  grading: { settled: (s) => s.state !== "EVALUATING", timeoutMs: 10 * 60_000 },
  // Our clock says time's up; ask until the server agrees (clocks drift).
  deadline: { settled: (s) => s.state !== "IN_PROGRESS", timeoutMs: 2 * 60_000 },
};

function waitPhaseOf(session: Session, deadlinePassed: boolean): WaitPhase | null {
  if (PREPARING.includes(session.state)) return "preparing";
  if (session.state === "EVALUATING") return "grading";
  if (session.state === "IN_PROGRESS" && deadlinePassed) return "deadline";
  return null;
}

/** How the current wait is going, for the line under the waiting screens. */
type WaitHealth = "ok" | "reconnecting" | "slow";

export default function InterviewSessionPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const router = useRouter();

  const [session, setSession] = useState<Session | null>(null);
  const [question, setQuestion] = useState<Question | null>(null);
  const [answer, setAnswer] = useState("");
  const [outOfQuestions, setOutOfQuestions] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<WaitHealth>("ok");
  const [confirmFinish, setConfirmFinish] = useState(false);
  // Bumped by "Keep waiting" to restart a wait that gave up.
  const [waitRound, setWaitRound] = useState(0);

  // Answer telemetry — the backend stores these alongside the answer. All
  // three are reset in loadQuestion, so their initial values are never read.
  const startedAt = useRef(0);
  const pasteEvents = useRef(0);
  const keystrokes = useRef(0);

  const countdown = useCountdown(session?.expires_at ?? null);
  const phase = session ? waitPhaseOf(session, countdown?.passed ?? false) : null;

  const loadQuestion = useCallback(async () => {
    try {
      const q = await nextQuestion(sessionId);
      setQuestion(q);
      setOutOfQuestions(false);
      setAnswer("");
      startedAt.current = Date.now();
      pasteEvents.current = 0;
      keystrokes.current = 0;
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        // Not an error: no unanswered questions left means the interview is over.
        setQuestion(null);
        setOutOfQuestions(true);
      } else {
        setError(describeError(err, "Could not load the question"));
      }
    }
  }, [sessionId]);

  // Initial load.
  useEffect(() => {
    let cancelled = false;
    getSession(sessionId)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        if (s.state === "IN_PROGRESS") void loadQuestion();
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err, "Could not load this interview"));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, loadQuestion]);

  // Whenever the page is in a waiting phase, poll until the state moves on.
  // Keyed on the *phase*, not the session object, so a fresh copy of the same
  // state doesn't restart the wait.
  useEffect(() => {
    if (!phase) return;
    const controller = new AbortController();
    const { settled, timeoutMs } = WAITS[phase];

    pollUntil(() => getSession(sessionId), settled, {
      signal: controller.signal,
      timeoutMs,
      onConnectionChange: (problem) => setHealth(problem ? "reconnecting" : "ok"),
    })
      .then((latest) => {
        setSession(latest);
        if (latest.state === "COMPLETED" || latest.state === "NEEDS_HUMAN_REVIEW") {
          router.replace(`/reports/${sessionId}`);
        }
      })
      .catch((err) => {
        if (isAbort(err)) return;
        if (err instanceof PollTimeout) {
          setHealth("slow");
        } else {
          setError(describeError(err, "Lost track of this interview"));
        }
      });

    return () => controller.abort();
  }, [phase, waitRound, sessionId, router]);

  function keepWaiting() {
    setHealth("ok");
    setWaitRound((n) => n + 1);
  }

  /**
   * A 409 means the server's state moved under us — most often the deadline
   * passed. Re-read the session so the page shows the state the server holds,
   * instead of an error on top of a screen that no longer applies.
   */
  async function recoverFrom(err: unknown, fallback: string) {
    if (err instanceof ApiError && err.status === 409) {
      try {
        setSession(await getSession(sessionId));
        return;
      } catch {
        /* fall through to the message */
      }
    }
    setError(describeError(err, fallback));
  }

  async function send() {
    if (!question || busy || answer.trim().length === 0) return;
    setBusy(true);
    setError(null);
    try {
      await submitAnswer(
        sessionId,
        {
          question_id: question.id,
          text: answer,
          time_taken_ms: Date.now() - startedAt.current,
          paste_events: pasteEvents.current,
          keystroke_count: keystrokes.current,
        },
        // Derived from *what* is being answered, not *when*: a double-click, a
        // retry after a dropped connection, and a second tab on the same
        // question all send the same key, so the backend stores one answer.
        `answer:${question.id}`,
      );
      setSession(await getSession(sessionId));
      await loadQuestion();
    } catch (err) {
      await recoverFrom(err, "Could not submit the answer");
    } finally {
      setBusy(false);
    }
  }

  async function finish() {
    setBusy(true);
    setError(null);
    setConfirmFinish(false);
    try {
      setSession(await finishSession(sessionId));
    } catch (err) {
      await recoverFrom(err, "Could not finish");
    } finally {
      setBusy(false);
    }
  }

  async function begin() {
    setBusy(true);
    setError(null);
    try {
      setSession(await startSession(sessionId));
      await loadQuestion();
    } catch (err) {
      await recoverFrom(err, "Could not start");
    } finally {
      setBusy(false);
    }
  }

  // One early return per region of the state machine, happy path last.

  if (!session) {
    if (error) {
      return (
        <Shell width="narrow">
          <ErrorBanner message={error} />
        </Shell>
      );
    }
    return <PageLoading width="medium" />;
  }

  if (session.state === "EVALUATING") {
    return <Scoring session={session} health={health} onKeepWaiting={keepWaiting} />;
  }

  if (session.state === "COMPLETED" || session.state === "NEEDS_HUMAN_REVIEW") {
    return (
      <Shell width="narrow">
        <Card className="flex flex-col items-start gap-4 p-8">
          <span className="flex size-12 items-center justify-center rounded-2xl bg-ok-subtle text-ok">
            <CircleCheckBig aria-hidden="true" className="size-6" />
          </span>
          <h1 className="font-display text-[28px] font-bold tracking-[-0.02em]">
            Your report is ready
          </h1>
          <Link href={`/reports/${sessionId}`} className={buttonClass("primary")}>
            View report
          </Link>
        </Card>
      </Shell>
    );
  }

  if (session.state === "EXPIRED" || session.state === "FAILED") {
    const expired = session.state === "EXPIRED";
    return (
      <Shell width="narrow">
        <Card className="flex flex-col items-start gap-4 p-8">
          <StatusPill state={session.state} />
          <span className="flex size-12 items-center justify-center rounded-2xl bg-bad-subtle text-bad">
            {expired ? (
              <Hourglass aria-hidden="true" className="size-6" />
            ) : (
              <TriangleAlert aria-hidden="true" className="size-6" />
            )}
          </span>
          <h1 className="font-display text-[28px] font-bold tracking-[-0.02em]">
            {expired ? "Time ran out" : "This interview couldn't be prepared"}
          </h1>
          <p className="text-ink-2">
            {session.failure_reason ??
              "The deadline passed before the interview was finished."}
          </p>
          <Link href="/interview" className={buttonClass("primary")}>
            Start a new interview
          </Link>
        </Card>
      </Shell>
    );
  }

  if (PREPARING.includes(session.state)) {
    return (
      <Shell width="narrow">
        <Card className="flex flex-col gap-6 p-8 sm:p-10">
          <div className="flex flex-col gap-2.5">
            <StatusPill state={session.state} />
            <h1 className="font-display text-[30px] leading-tight font-bold tracking-[-0.02em]">
              Writing your questions
            </h1>
            <p className="text-ink-2">
              Each question comes from a skill on your resume, along with what a good
              answer should cover — decided before you write a word.
            </p>
          </div>
          <div className="flex flex-col gap-3" aria-hidden="true">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 * i, duration: 0.4, ease: EASE }}
                className="flex items-center gap-3 rounded-[14px] border border-line-soft bg-subtle px-4 py-3.5"
              >
                <Sparkles className="size-4 shrink-0 text-accent" />
                <Skeleton className="h-3 flex-1" />
              </motion.div>
            ))}
          </div>
          <WaitNotice health={health} onKeepWaiting={keepWaiting}>
            Question writing is taking longer than usual. It&apos;s still running on the
            server — this page is safe to reload or come back to.
          </WaitNotice>
        </Card>
      </Shell>
    );
  }

  if (session.state === "READY") {
    return (
      <Shell width="medium">
        <Card className="flex flex-col gap-7 p-8 sm:p-10">
          <div className="flex flex-col gap-3">
            <StatusPill state={session.state} />
            <h1 className="font-display text-[34px] leading-[1.15] font-bold tracking-[-0.02em]">
              {session.total_questions} questions ready
            </h1>
            {session.topics.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-sm text-ink-3">Covering</span>
                {session.topics.map((topic) => (
                  <Tag key={topic}>{topic}</Tag>
                ))}
              </div>
            )}
          </div>

          <ul className="grid gap-3 sm:grid-cols-3">
            {[
              {
                icon: <Timer aria-hidden="true" className="size-5" />,
                title: "Timed on our side",
                body: "The clock starts when you press Start. Closing the tab doesn't pause it.",
              },
              {
                icon: <ListChecks aria-hidden="true" className="size-5" />,
                title: "One at a time",
                body: "Submitted answers are final; the next question loads straight after.",
              },
              {
                icon: <ClipboardPaste aria-hidden="true" className="size-5" />,
                title: "Typing is noted",
                body: "Keystrokes and paste events are recorded with each answer.",
              },
            ].map((rule) => (
              <li
                key={rule.title}
                className="flex flex-col gap-2 rounded-[14px] border border-line-soft bg-subtle p-4 transition-[border-color,transform] duration-250 hover:-translate-y-0.5 hover:border-accent-mid"
              >
                <span className="flex size-9 items-center justify-center rounded-[10px] bg-accent-subtle text-accent">
                  {rule.icon}
                </span>
                <span className="font-semibold">{rule.title}</span>
                <span className="text-sm text-ink-2">{rule.body}</span>
              </li>
            ))}
          </ul>

          {error && <ErrorBanner message={error} />}

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-6">
            <Link href="/interview" className="text-sm font-semibold text-ink-2 hover:text-ink">
              Not now
            </Link>
            <Button size="lg" onClick={begin} loading={busy}>
              {busy ? "Starting…" : "Start interview"}
            </Button>
          </div>
        </Card>
      </Shell>
    );
  }

  // IN_PROGRESS — the interview itself.
  const answered = session.answered;
  const total = session.total_questions || 1;
  const remaining = Math.max(0, total - answered);

  return (
    <Shell width="medium">
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-[260px] flex-1 flex-col gap-2.5">
            <span className="tabular font-semibold">
              {outOfQuestions
                ? `All ${total} answered`
                : `Question ${Math.min(answered + 1, total)} of ${total}`}
            </span>
            <div
              role="progressbar"
              aria-label="Interview progress"
              aria-valuemin={0}
              aria-valuemax={total}
              aria-valuenow={answered}
              className="grid max-w-[320px] gap-1.5"
              style={{ gridTemplateColumns: `repeat(${total}, minmax(0, 1fr))` }}
            >
              {Array.from({ length: total }, (_, i) => (
                <span key={i} className="h-1.5 overflow-hidden rounded-full bg-line">
                  <motion.span
                    className={`block h-full rounded-full ${
                      i < answered ? "bg-accent" : "bg-accent-mid"
                    }`}
                    initial={false}
                    animate={{ width: i < answered || (i === answered && !outOfQuestions) ? "100%" : "0%" }}
                    transition={{ duration: 0.5, ease: EASE }}
                  />
                </span>
              ))}
            </div>
          </div>
          {countdown && <TimerChip countdown={countdown} />}
        </div>

        {error && <ErrorBanner message={error} />}

        <AnimatePresence mode="wait" initial={false}>
          {question && (
            <motion.div
              key={question.id}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.35, ease: EASE }}
            >
              <Card as="section" aria-labelledby="q" className="flex flex-col gap-6 p-6 sm:p-8">
                <div className="flex flex-col gap-3.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <Chip tone="accent">{question.topic}</Chip>
                    <Chip>{question.difficulty}</Chip>
                  </div>
                  <h1
                    id="q"
                    className="max-w-[34ch] font-display text-[24px] leading-[1.25] font-semibold tracking-[-0.01em] sm:text-[28px]"
                  >
                    {question.text}
                  </h1>
                </div>

                <div className="flex flex-col gap-2">
                  <label htmlFor="answer" className="font-semibold">
                    Your answer
                  </label>
                  <textarea
                    id="answer"
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                    onKeyDown={(e) => {
                      // Ctrl/⌘+Enter submits — and, being a shortcut, isn't a keystroke.
                      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                        e.preventDefault();
                        void send();
                        return;
                      }
                      if (countsAsKeystroke(e)) keystrokes.current += 1;
                    }}
                    onPaste={() => {
                      pasteEvents.current += 1;
                    }}
                    disabled={busy}
                    rows={9}
                    className={`${FIELD_CLASS} resize-y p-4 text-base leading-[1.6]`}
                  />
                  <div className="flex flex-wrap justify-between gap-2 text-[13px] text-ink-3">
                    <span>Explain your reasoning. Code is welcome.</span>
                    <span className="tabular">
                      {answer.length.toLocaleString()} characters
                    </span>
                  </div>
                </div>

                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line-soft pt-6">
                  <Button
                    variant="secondary"
                    onClick={() => setConfirmFinish(true)}
                    disabled={busy}
                  >
                    Finish early
                  </Button>
                  <div className="flex items-center gap-3">
                    <span className="hidden text-xs text-ink-3 sm:inline">
                      Ctrl + Enter
                    </span>
                    <Button
                      onClick={send}
                      loading={busy}
                      disabled={answer.trim().length === 0}
                    >
                      {busy ? "Submitting…" : "Submit answer"}
                    </Button>
                  </div>
                </div>
              </Card>
            </motion.div>
          )}

          {outOfQuestions && (
            <motion.div
              key="done"
              initial={{ opacity: 0, scale: 0.97 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.4, ease: EASE }}
            >
              <Card className="flex flex-col items-start gap-5 p-8 sm:flex-row sm:items-center">
                <motion.span
                  initial={{ scale: 0.4, rotate: -20 }}
                  animate={{ scale: 1, rotate: 0 }}
                  transition={{ type: "spring", stiffness: 300, damping: 16, delay: 0.1 }}
                  className="flex size-12 shrink-0 items-center justify-center rounded-full bg-accent text-ink-inv"
                >
                  <Check aria-hidden="true" className="size-6" strokeWidth={3} />
                </motion.span>
                <div className="flex flex-1 flex-col gap-1">
                  <span className="text-lg font-semibold">That was the last question.</span>
                  <span className="text-ink-2">
                    Finishing hands your answers to the graders. It cannot be undone.
                  </span>
                </div>
                <Button size="lg" onClick={finish} loading={busy}>
                  {busy ? "Finishing…" : "Finish interview"}
                </Button>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>

        <p className="max-w-[70ch] text-sm text-ink-3">
          Each answer is saved the moment you submit it. The deadline is kept on our side,
          so refreshing or closing this page doesn&apos;t change your time.
        </p>
      </div>

      <AnimatePresence>
        {confirmFinish && (
          <ConfirmFinish
            remaining={remaining}
            busy={busy}
            onCancel={() => setConfirmFinish(false)}
            onConfirm={finish}
          />
        )}
      </AnimatePresence>
    </Shell>
  );
}

function TimerChip({
  countdown,
}: {
  countdown: { label: string; passed: boolean; urgent: boolean };
}) {
  if (countdown.passed) {
    return (
      <div className="flex items-center gap-2.5 rounded-control border border-[#efc6c2] bg-bad-subtle px-4 py-2.5 text-sm font-semibold text-bad">
        <Hourglass aria-hidden="true" className="size-[18px]" />
        Time&apos;s up — checking with the server…
      </div>
    );
  }
  return (
    <div
      role="timer"
      aria-label="Time left"
      className={`flex items-center gap-2.5 rounded-control border px-4 py-2.5 transition-colors duration-300 ${
        countdown.urgent ? "border-warn-line bg-warn-subtle" : "border-line bg-surface"
      }`}
    >
      <motion.span
        animate={countdown.urgent ? { rotate: [0, -12, 12, 0] } : { rotate: 0 }}
        transition={countdown.urgent ? { duration: 0.6, repeat: Infinity, repeatDelay: 2 } : {}}
        className={countdown.urgent ? "text-warn" : "text-accent"}
      >
        <Timer aria-hidden="true" className="size-[18px]" />
      </motion.span>
      <span
        className={`tabular font-display text-[22px] font-bold tracking-[0.01em] ${
          countdown.urgent ? "text-warn" : "text-ink"
        }`}
      >
        {countdown.label}
      </span>
      <span className="text-sm text-ink-3">left</span>
    </div>
  );
}

/** "Finish now?" — only asked when questions are still unanswered. */
function ConfirmFinish({
  remaining,
  busy,
  onCancel,
  onConfirm,
}: {
  remaining: number;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const titleId = useId();

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-inverse/50 px-4 backdrop-blur-[2px]"
      onClick={() => !busy && onCancel()}
    >
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        initial={{ opacity: 0, y: 16, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 8, scale: 0.98 }}
        transition={{ duration: 0.25, ease: EASE }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[460px]"
      >
        <Card className="flex flex-col gap-5 p-7">
          <span className="flex size-11 items-center justify-center rounded-xl bg-warn-subtle text-warn">
            <TriangleAlert aria-hidden="true" className="size-5" />
          </span>
          <div className="flex flex-col gap-1.5">
            <h2 id={titleId} className="font-display text-[22px] font-bold">
              Finish with {remaining} question{remaining === 1 ? "" : "s"} unanswered?
            </h2>
            <p className="text-ink-2">
              Unanswered questions score zero. Your submitted answers go to the graders
              and the interview can&apos;t be resumed.
            </p>
          </div>
          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="secondary" onClick={onCancel} disabled={busy} autoFocus>
              Keep answering
            </Button>
            <Button variant="danger" onClick={onConfirm} loading={busy}>
              Finish now
            </Button>
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
}

/**
 * Keys that type or delete text. Shortcuts (Ctrl+V, Ctrl+A), bare modifiers
 * and navigation keys would otherwise inflate the count — and a paste would
 * register as a keystroke *and* a paste event.
 */
function countsAsKeystroke(e: React.KeyboardEvent): boolean {
  if (e.ctrlKey || e.metaKey || e.altKey) return false;
  return e.key.length === 1 || e.key === "Backspace" || e.key === "Delete" || e.key === "Enter";
}

/**
 * The line under a waiting screen. Silent while all is well; "reconnecting"
 * during a network blip; and, once polling gives up, the slow-path message
 * plus a way to resume — never a dead end.
 */
function WaitNotice({
  health,
  onKeepWaiting,
  children,
}: {
  health: WaitHealth;
  onKeepWaiting: () => void;
  children: React.ReactNode;
}) {
  if (health === "ok") return null;
  if (health === "reconnecting") {
    return (
      <p role="status" className="text-sm text-ink-3">
        Connection lost — reconnecting…
      </p>
    );
  }
  return (
    <Notice
      tone="warn"
      action={
        <Button size="sm" variant="secondary" onClick={onKeepWaiting}>
          Keep waiting
        </Button>
      }
    >
      {children}
    </Notice>
  );
}

/** The "Scoring your interview" screen: a vertical stepper while the worker grades. */
function Scoring({
  session,
  health,
  onKeepWaiting,
}: {
  session: Session;
  health: WaitHealth;
  onKeepWaiting: () => void;
}) {
  const steps = [
    {
      label: "Answers submitted",
      detail: `${session.answered} of ${session.total_questions} received`,
      state: "done",
    },
    { label: "Grading each answer twice", detail: "In progress", state: "active" },
    { label: "Checking where the two grades disagree", state: "todo" },
    { label: "Building your report", state: "todo" },
  ] as const;

  return (
    <Shell width="narrow" className="sm:pt-[72px]">
      <div className="flex flex-col gap-5">
        <Card as="section" aria-labelledby="t" className="flex flex-col gap-7 rounded-[24px] p-7 sm:p-10">
          <div className="flex flex-col gap-2.5">
            <StatusPill state="EVALUATING" />
            <h1
              id="t"
              className="font-display text-[30px] leading-[1.15] font-bold tracking-[-0.02em] sm:text-[34px]"
            >
              Scoring your interview
            </h1>
            <p className="text-base text-ink-2">
              Every answer is graded twice, independently. If the two grades disagree, a
              recruiter reads it instead of averaging them.
            </p>
          </div>

          <ol className="flex flex-col">
            {steps.map((step, i) => (
              <motion.li
                key={step.label}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 + i * 0.12, duration: 0.4, ease: EASE }}
                aria-current={step.state === "active" ? "step" : undefined}
                className="flex items-start gap-4"
              >
                <div className="flex flex-col items-center">
                  {step.state === "done" && (
                    <span className="flex size-8 items-center justify-center rounded-full bg-accent text-ink-inv">
                      <Check aria-hidden="true" className="size-4" strokeWidth={3} />
                    </span>
                  )}
                  {step.state === "active" && (
                    <span className="relative flex size-8 items-center justify-center rounded-full border-[3px] border-accent bg-accent-subtle">
                      <motion.span
                        className="absolute inset-[-3px] rounded-full border-2 border-accent"
                        animate={{ scale: [1, 1.45], opacity: [0.6, 0] }}
                        transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }}
                      />
                      <span className="size-2.5 rounded-full bg-accent" />
                    </span>
                  )}
                  {step.state === "todo" && (
                    <span className="size-8 rounded-full border-2 border-[#c9d6d7] bg-surface" />
                  )}
                  {i < steps.length - 1 && (
                    <span
                      className={`h-7 w-0.5 ${step.state === "done" ? "bg-accent" : "bg-line"}`}
                    />
                  )}
                </div>
                <div className="pt-1">
                  <div
                    className={
                      step.state === "todo" ? "font-medium text-ink-2" : "font-semibold text-ink"
                    }
                  >
                    {step.label}
                  </div>
                  {"detail" in step && (
                    <div
                      className={`text-sm ${step.state === "active" ? "text-accent-strong" : "text-ink-3"}`}
                    >
                      {step.detail}
                    </div>
                  )}
                </div>
              </motion.li>
            ))}
          </ol>

          <WaitNotice health={health} onKeepWaiting={onKeepWaiting}>
            Grading is taking longer than usual. Your answers are saved — your report will
            show the result when it&apos;s done.
          </WaitNotice>

          <div className="flex items-start gap-3 rounded-[14px] bg-canvas p-4">
            <Info aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-accent" />
            <p className="text-sm text-ink-2">
              You can close this tab. Your result is saved either way, and it will be
              waiting under My interviews.
            </p>
          </div>
        </Card>

        <FadeIn delay={0.5} className="self-center">
          <Link
            href="/interview"
            className="font-semibold text-accent underline-offset-[3px] hover:text-brand hover:underline"
          >
            Back to my interviews
          </Link>
        </FadeIn>
      </div>
    </Shell>
  );
}
