"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import {
  ChartNoAxesColumn,
  ChevronRight,
  CircleCheck,
  ClipboardList,
  FileText,
  Hourglass,
  Layers,
  Loader2,
  Plus,
  Sparkles,
  Upload,
} from "lucide-react";
import {
  createResume,
  createSession,
  uploadResume,
  describeError,
  getResume,
  listMySessions,
  RESUME_EXTENSIONS,
  resumeProblem,
  type Resume,
  type SessionSummary,
} from "@/lib/api";
import { formatBytes, humanWhen, minutesLeft, sessionName, toHundred } from "@/lib/format";
import { peekPendingResume, takePendingResume } from "@/lib/pending-resume";
import { isAbort, pollUntil, PollTimeout, WORKER_WAIT_MS } from "@/lib/poll";
import { CountUp, EASE, MiniScoreRing, Stagger, StaggerItem } from "@/components/motion";
import { HeroTile, PageHero } from "@/components/page-hero";
import {
  Button,
  Card,
  EmptyState,
  ErrorBanner,
  FIELD_CLASS,
  MeterRow,
  Notice,
  Shell,
  Skeleton,
  StatusPill,
  Tag,
} from "@/components/ui";

/**
 * compose → parsing → parsed → creating. Errors step *back*, so the person
 * gets their textarea or button returned to them. `slow` is the fourth exit
 * of the parse wait: the worker is still going, we just stopped watching.
 */
type Stage = "compose" | "parsing" | "slow" | "parsed" | "creating";

/** How long "Creating…" may wait on a client navigation before a full page load. */
const NAVIGATION_FALLBACK_MS = 6000;

/**
 * The candidate's past and in-flight interviews, loaded once — this is a list
 * to pick from, not a live view, so it doesn't poll. Fetched here rather than
 * in the list because the hero's numbers come from the same rows.
 */
export default function MyInterviewsPage() {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listMySessions()
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch((err) => {
        // The list is a convenience beside the real task (starting an
        // interview); if it fails, say so and leave the form usable.
        if (!cancelled) {
          setSessions([]);
          setError(describeError(err, "Could not load your interviews"));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <PageHero
        eyebrow="Your dashboard"
        title="My interviews"
        subtitle="Practise on questions written from your own resume, then see where you stand by topic."
        actions={
          // On a phone the start card sits below the list; this jumps to it.
          <a
            href="#new-interview"
            className="group inline-flex min-h-12 items-center gap-2 rounded-full bg-white px-6 text-[15px] font-semibold text-brand shadow-[0_16px_40px_-16px_rgba(0,0,0,0.6)] transition-[transform,background] duration-250 ease-out-soft hover:-translate-y-0.5 hover:bg-accent-soft lg:hidden"
          >
            <Plus
              aria-hidden="true"
              className="size-4.5 transition-transform duration-250 group-hover:rotate-90"
            />
            New interview
          </a>
        }
      >
        <InterviewStats sessions={sessions} />
      </PageHero>
      <Shell>
        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <RecentSessions sessions={sessions} error={error} />
          <NewInterview />
        </div>
      </Shell>
    </>
  );
}

const OPEN_STATES = new Set([
  "CREATED",
  "PARSING",
  "GENERATING_QS",
  "READY",
  "IN_PROGRESS",
  "EVALUATING",
]);

/** Four numbers for the hero, all derived from the session list. */
function InterviewStats({ sessions }: { sessions: SessionSummary[] | null }) {
  if (sessions === null) {
    return (
      <div aria-hidden="true" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="h-21.5 animate-pulse rounded-2xl bg-white/8" />
        ))}
      </div>
    );
  }
  const finished = sessions.filter(
    (s) => s.state === "COMPLETED" || s.state === "NEEDS_HUMAN_REVIEW",
  );
  const scores = finished.flatMap((s) => (s.overall == null ? [] : [toHundred(s.overall)]));
  const average = scores.length
    ? Math.round(scores.reduce((sum, score) => sum + score, 0) / scores.length)
    : null;
  const open = sessions.filter((s) => OPEN_STATES.has(s.state)).length;

  return (
    <Stagger className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StaggerItem>
        <HeroTile
          icon={<Layers aria-hidden="true" className="size-4" />}
          label="Interviews"
          value={<CountUp value={sessions.length} />}
        />
      </StaggerItem>
      <StaggerItem>
        <HeroTile
          icon={<CircleCheck aria-hidden="true" className="size-4" />}
          label="Finished"
          value={<CountUp value={finished.length} />}
        />
      </StaggerItem>
      <StaggerItem>
        <HeroTile
          icon={<Hourglass aria-hidden="true" className="size-4" />}
          label="In progress"
          value={<CountUp value={open} />}
        />
      </StaggerItem>
      <StaggerItem>
        <HeroTile
          icon={<ChartNoAxesColumn aria-hidden="true" className="size-4" />}
          label="Average score"
          value={
            average === null ? (
              "—"
            ) : (
              <>
                <CountUp value={average} />
                <span className="text-base font-semibold text-ink-on-dark">/100</span>
              </>
            )
          }
        />
      </StaggerItem>
    </Stagger>
  );
}

// --- Left: the candidate's interviews --------------------------------------

function RecentSessions({
  sessions,
  error,
}: {
  sessions: SessionSummary[] | null;
  error: string | null;
}) {
  return (
    <section aria-labelledby="recent" className="flex min-w-0 flex-1 flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h2 id="recent" className="text-[17px] font-semibold text-ink">
          Recent sessions
        </h2>
        {sessions && sessions.length > 0 && (
          <span className="tabular text-sm text-ink-3">
            {sessions.length} session{sessions.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {error && <ErrorBanner message={error} />}

      {sessions === null && (
        <div className="flex flex-col gap-3">
          <span className="sr-only" role="status">
            Loading your interviews…
          </span>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-23 w-full rounded-row" />
          ))}
        </div>
      )}

      {sessions?.length === 0 && !error && (
        <EmptyState
          icon={<ClipboardList aria-hidden="true" className="size-6" />}
          title="No interviews yet"
        >
          Add your resume and we&apos;ll write your first set of questions from the skills
          you list.
        </EmptyState>
      )}

      {sessions && sessions.length > 0 && (
        <Stagger className="flex flex-col gap-3">
          {sessions.map((session) => (
            <StaggerItem key={session.id}>
              <SessionRow session={session} />
            </StaggerItem>
          ))}
        </Stagger>
      )}
    </section>
  );
}

const ROW =
  "group flex flex-wrap items-center gap-5 rounded-card border bg-surface px-5.5 py-5 text-ink " +
  "transition-[transform,box-shadow,border-color] duration-250 ease-out-soft";
const ROW_LINK = "hover:-translate-y-0.5 hover:border-accent-mid hover:shadow-lift";

function SessionRow({ session }: { session: SessionSummary }) {
  const name = (
    <div className="flex flex-wrap items-center gap-2.5">
      <span className="text-base font-semibold">Session {sessionName(session.id)}</span>
      <StatusPill state={session.state} />
    </div>
  );
  const tags = (extra?: React.ReactNode) =>
    session.topics.length > 0 || extra ? (
      <div className="flex flex-wrap items-center gap-1.5">
        {session.topics.slice(0, 4).map((topic) => (
          <Tag key={topic}>{topic}</Tag>
        ))}
        {session.topics.length > 4 && <Tag>+{session.topics.length - 4}</Tag>}
        {extra}
      </div>
    ) : null;

  switch (session.state) {
    case "IN_PROGRESS": {
      const left = session.expires_at ? minutesLeft(session.expires_at) : null;
      return (
        <Link
          href={`/interview/${session.id}`}
          className={`${ROW} ${ROW_LINK} border-accent shadow-[0_0_0_4px_var(--color-accent-subtle)]`}
        >
          <div className="flex min-w-60 flex-1 flex-col gap-2">
            {name}
            {tags()}
          </div>
          <div className="flex flex-col items-end gap-1.5 max-sm:w-full max-sm:flex-row max-sm:items-center max-sm:justify-between">
            <span className="tabular text-sm text-ink-2">
              Question {Math.min(session.answered + 1, session.total_questions)} of{" "}
              {session.total_questions}
              {left !== null && `, ${left} min left`}
            </span>
            <span className="btn-brand rounded-full px-4.5 py-2.5 text-sm font-semibold transition-[background,box-shadow,transform] duration-200">
              Continue interview
            </span>
          </div>
        </Link>
      );
    }

    case "READY":
      return (
        <Link href={`/interview/${session.id}`} className={`${ROW} ${ROW_LINK} border-line shadow-card`}>
          <div className="flex min-w-60 flex-1 flex-col gap-2">
            {name}
            {tags()}
          </div>
          <div className="flex flex-col items-end gap-1.5 max-sm:w-full max-sm:flex-row max-sm:items-center max-sm:justify-between">
            <span className="tabular text-sm text-ink-2">
              {session.total_questions} questions ready
            </span>
            <span className="btn-brand rounded-full px-4.5 py-2.5 text-sm font-semibold transition-[background,box-shadow,transform] duration-200">
              Start interview
            </span>
          </div>
        </Link>
      );

    case "COMPLETED":
    case "NEEDS_HUMAN_REVIEW": {
      const reviewing = session.state === "NEEDS_HUMAN_REVIEW";
      const when = session.updated_at ?? session.created_at;
      return (
        <Link href={`/reports/${session.id}`} className={`${ROW} ${ROW_LINK} border-line shadow-card`}>
          <div className="flex min-w-60 flex-1 flex-col gap-2">
            {name}
            {tags(
              <span className="ml-1 text-[13px] text-ink-3">Finished {humanWhen(when)}</span>,
            )}
          </div>
          <div className="flex items-center gap-4.5">
            {session.overall != null && (
              <div className="flex items-center gap-3">
                <MiniScoreRing pct={toHundred(session.overall)} />
                <div className="flex flex-col">
                  <span className="tabular text-sm font-semibold text-ink">
                    {toHundred(session.overall)}
                    <span className="font-medium text-ink-3">/100</span>
                  </span>
                  <span className={`text-[13px] ${reviewing ? "text-warn" : "text-ink-3"}`}>
                    {reviewing ? "May change after review" : "Overall"}
                  </span>
                </div>
              </div>
            )}
            <span className="flex items-center gap-1 text-sm font-semibold text-accent transition-colors group-hover:text-brand">
              View report
              <ChevronRight
                aria-hidden="true"
                className="size-4 transition-transform duration-250 group-hover:translate-x-0.75"
              />
            </span>
          </div>
        </Link>
      );
    }

    case "EVALUATING":
    case "CREATED":
    case "PARSING":
    case "GENERATING_QS":
      return (
        <Link href={`/interview/${session.id}`} className={`${ROW} ${ROW_LINK} border-line shadow-card`}>
          <div className="flex min-w-60 flex-1 flex-col gap-2">
            {name}
            {tags()}
          </div>
          <span className="flex items-center gap-2 text-sm text-ink-2">
            <Loader2 aria-hidden="true" className="size-4 animate-spin text-accent" />
            {session.state === "EVALUATING" ? "Scoring your answers" : "Writing your questions"}
            <ChevronRight
              aria-hidden="true"
              className="size-4 text-accent transition-transform duration-250 group-hover:translate-x-0.75"
            />
          </span>
        </Link>
      );

    case "EXPIRED":
    case "FAILED":
      return (
        <div className={`${ROW} border-line`}>
          <div className="flex flex-1 flex-col gap-2">
            {name}
            <span className="text-[13px] text-ink-3">
              {session.state === "EXPIRED"
                ? "Time ran out before the interview was finished."
                : (session.failure_reason ?? "This interview could not be prepared.")}{" "}
              Started {humanWhen(session.created_at)}.
            </span>
          </div>
        </div>
      );
  }
}

// --- Right: start a new interview ------------------------------------------

function NewInterview() {
  const router = useRouter();
  const [source, setSource] = useState<"file" | "paste">("file");
  // A resume chosen on the landing page: choosing it there *was* the request
  // to upload, so the card opens already reading it instead of asking again.
  // Read once at mount — this page only renders in the browser, after sign-in.
  const [arrived] = useState(() => peekPendingResume());
  const [file, setFile] = useState<File | null>(arrived);
  const [text, setText] = useState("");
  const [stage, setStage] = useState<Stage>(arrived ? "parsing" : "compose");
  const [resume, setResume] = useState<Resume | null>(null);
  // What the resume came from, for the "Skills we found" header.
  const [origin, setOrigin] = useState<string>(arrived?.name ?? "pasted text");
  // Optional. Empty means "interview me on what my résumé claims".
  const [jobDescription, setJobDescription] = useState("");
  // The resume being parsed. Kept across a timeout so "keep waiting" watches
  // the same row instead of uploading (and paying for) the text again.
  const [pendingResumeId, setPendingResumeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Polling runs from click handlers, not an effect, so stop it by hand when
  // the page goes away.
  const polling = useRef<AbortController | null>(null);
  useEffect(() => () => polling.current?.abort(), []);

  async function waitForParse(resumeId: string) {
    setError(null);
    setStage("parsing");
    polling.current?.abort();
    const controller = new AbortController();
    polling.current = controller;
    try {
      const parsed = await pollUntil(
        () => getResume(resumeId),
        // Settled, not succeeded: polling for "parsed" alone would spin for
        // minutes on a failure the server knew about in 200 ms.
        (r) => r.parse_status === "parsed" || r.parse_status === "failed",
        // Long enough to outlast the worker's retry schedule (30+60+120+240s),
        // so the server's verdict — and its reason — actually reaches the user
        // instead of the generic "taking a while" notice winning the race.
        { signal: controller.signal, timeoutMs: WORKER_WAIT_MS },
      );
      setPendingResumeId(null);
      if (parsed.parse_status === "failed") {
        // Prefer the server's reason. It knows whether the cause clears in
        // minutes or in hours, and telling someone to retype their resume when
        // the real problem is a provider quota wastes their time.
        setError(
          parsed.failure_reason ??
            "We could not read that resume. Try pasting the plain text again.",
        );
        setStage("compose");
        return;
      }
      setResume(parsed);
      setStage("parsed");
    } catch (err) {
      if (isAbort(err)) return;
      if (err instanceof PollTimeout) {
        setStage("slow");
        return;
      }
      setPendingResumeId(null);
      setError(describeError(err, "Could not check on your resume"));
      setStage("compose");
    }
  }

  /** Check what we can (extension, size) before sending anything. */
  function pickFile(candidate: File | undefined) {
    if (!candidate) return;
    const problem = resumeProblem(candidate);
    setError(problem);
    if (!problem) setFile(candidate);
  }

  /** Paste and file differ only in how the resume row gets created. */
  async function submit(create: () => Promise<Resume>, from: string) {
    setError(null);
    setOrigin(from);
    setStage("parsing");
    try {
      const created = await create();
      setPendingResumeId(created.id);
      await waitForParse(created.id);
    } catch (err) {
      // 413 / 415 / 422 carry a sentence from the backend ("No readable text
      // found … paste the text instead"), so describeError passes it through.
      setError(describeError(err, "Upload failed"));
      setStage("compose");
    }
  }

  /**
   * Create the session and hand over to its own page straight away. That page
   * waits for the questions, so the session's URL — not this component's
   * memory — is what survives a slow worker, a reload, or a closed tab.
   */
  async function generate() {
    if (!resume) return;
    setError(null);
    setStage("creating");
    try {
      const session = await createSession(resume.id, jobDescription);
      const target = `/interview/${session.id}`;
      router.push(target);
      // A client-side navigation once stalled silently here: the session was
      // ready in five seconds, but the tab never requested the next page and sat
      // on "Creating…". If we are still here after a few seconds, load the page
      // the ordinary way. A no-op when the navigation already happened.
      window.setTimeout(() => {
        // A full load is the point: it is the fallback for a stalled router.push.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        if (window.location.pathname !== target) window.location.assign(target);
      }, NAVIGATION_FALLBACK_MS);
    } catch (err) {
      setError(describeError(err, "Could not create the interview"));
      setStage("parsed");
    }
  }

  function startOver() {
    polling.current?.abort();
    setResume(null);
    setFile(null);
    setPendingResumeId(null);
    setError(null);
    setStage("compose");
  }

  // The upload for a resume carried over from the landing page (see the state
  // above). `take` hands it out once, so Strict Mode's second effect run finds
  // nothing; every state change waits for the server's answer.
  const uploadOnArrival = useEffectEvent((pending: File) => {
    uploadResume(pending)
      .then((created) => {
        setPendingResumeId(created.id);
        return waitForParse(created.id);
      })
      .catch((err) => {
        setError(describeError(err, "Upload failed"));
        setStage("compose");
      });
  });
  useEffect(() => {
    const pending = takePendingResume();
    if (pending) uploadOnArrival(pending);
  }, []);

  const view = stage === "creating" ? "parsed" : stage;

  return (
    <Card
      as="aside"
      id="new-interview"
      aria-labelledby="new"
      className="relative flex w-full scroll-mt-28 flex-col gap-5 overflow-hidden p-6 shadow-[0_32px_64px_-36px_rgba(15,61,68,0.45)] sm:p-7 lg:sticky lg:top-24 lg:w-105 lg:shrink-0"
    >
      {/* The landing hero's lit hairline, along the card's top edge. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-6 top-0 h-px bg-linear-to-r from-transparent via-glow to-transparent"
      />
      <div className="flex items-start gap-4">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-2xl bg-linear-to-br from-glow to-accent text-white shadow-[0_10px_24px_-10px_rgba(10,117,112,0.7)]">
          <Sparkles aria-hidden="true" className="size-5" />
        </span>
        <div className="flex flex-col gap-1">
          <h2
            id="new"
            className="font-display text-2xl leading-tight font-bold tracking-[-0.01em] text-ink"
          >
            Start a new interview
          </h2>
          <p className="text-ink-2">
            We read your resume, pick out the skills you list, and write questions on them.
          </p>
        </div>
      </div>

      {error && <ErrorBanner message={error} />}

      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={view}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.28, ease: EASE }}
          className="flex flex-col gap-5"
        >
          {view === "compose" && (
            <>
              <SourceToggle value={source} onChange={setSource} />
              {source === "file" ? (
                <>
                  <FileDrop file={file} onPick={pickFile} />
                  <Button
                    size="lg"
                    onClick={() => file && submit(() => uploadResume(file), file.name)}
                    disabled={!file}
                  >
                    <Upload aria-hidden="true" className="size-4.5" />
                    Upload resume
                  </Button>
                </>
              ) : (
                <>
                  <div className="flex flex-col gap-2">
                    <textarea
                      aria-label="Resume text"
                      value={text}
                      onChange={(e) => setText(e.target.value)}
                      rows={10}
                      placeholder="Paste the full text of your resume — experience, projects, and the tools you used."
                      className={`${FIELD_CLASS} resize-y leading-6`}
                    />
                    <span className="tabular self-end text-[13px] text-ink-3">
                      {text.length.toLocaleString()} characters
                    </span>
                  </div>
                  <Button
                    size="lg"
                    onClick={() => submit(() => createResume(text), "pasted text")}
                    disabled={text.trim().length === 0}
                  >
                    Use this text
                  </Button>
                </>
              )}
            </>
          )}

          {view === "parsing" && (
            <div className="flex flex-col gap-4">
              <div className="flex items-center gap-3 rounded-[14px] bg-accent-soft px-4 py-3.5">
                <Loader2 aria-hidden="true" className="size-5 animate-spin text-accent" />
                <span role="status" className="text-sm font-medium text-ink">
                  Reading your resume and picking out skills…
                </span>
              </div>
              <div className="flex flex-col gap-3 px-1" aria-hidden="true">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="flex items-center gap-3">
                    <Skeleton className="h-3.5 w-24" />
                    <Skeleton className="h-1.5 flex-1" />
                    <Skeleton className="h-3.5 w-8" />
                  </div>
                ))}
              </div>
            </div>
          )}

          {view === "slow" && pendingResumeId && (
            <Notice
              tone="warn"
              title="Still reading your resume"
              action={
                <Button size="sm" variant="secondary" onClick={() => waitForParse(pendingResumeId)}>
                  Keep waiting
                </Button>
              }
            >
              {/* The old copy said the server was "still working on it", which
                  reads as "refresh in a moment". The common cause is the AI
                  provider rate-limiting us, and that can take hours to clear —
                  so say what is actually happening and offer a way to leave. */}
              This can take several minutes when the AI provider is busy or has rate-limited
              us. Your upload is saved either way — keep waiting, or come back to it from{" "}
              <span className="font-medium text-ink">My interviews</span> later.
            </Notice>
          )}

          {view === "parsed" && resume && (
            <>
              <div className="flex flex-col gap-3 border-t border-line-soft pt-4">
                <div className="flex items-center justify-between gap-3">
                  <span className="font-semibold text-ink">Skills we found</span>
                  <span className="flex min-w-0 items-center gap-1.5 text-[13px] text-ink-3">
                    <FileText aria-hidden="true" className="size-3.5 shrink-0" />
                    <span className="truncate">{origin}</span>
                  </span>
                </div>
                <div className="flex flex-col gap-2.5">
                  {resume.skills.map((skill, i) => (
                    <MeterRow
                      key={skill.name}
                      label={skill.name}
                      value={skill.confidence}
                      delay={0.05 * i}
                    />
                  ))}
                </div>
                <p className="text-[13px] text-ink-3">
                  Confidence shows how clearly each skill appears in your resume. Questions
                  follow these topics.
                </p>
              </div>

              {/* Optional. With a job description the interview probes what the
                  résumé does *not* evidence — asking about what is already on
                  the page largely wastes the questions. */}
              <details className="flex flex-col gap-2 border-t border-line-soft pt-4">
                <summary className="cursor-pointer list-none font-semibold text-ink marker:content-none">
                  Interviewing for a specific role?{" "}
                  <span className="font-normal text-ink-3">(optional)</span>
                </summary>
                <p className="mt-2 text-[13px] text-ink-3">
                  Paste the job description and we will focus on the requirements your
                  resume does not already cover.
                </p>
                <textarea
                  value={jobDescription}
                  onChange={(event) => setJobDescription(event.target.value)}
                  rows={6}
                  maxLength={20000}
                  placeholder={`- Build async Python services on PostgreSQL
- Operate Kubernetes clusters`}
                  className={`${FIELD_CLASS} mt-2 resize-y leading-relaxed`}
                />
              </details>

              <div className="flex flex-col gap-2">
                <Button size="lg" onClick={generate} loading={stage === "creating"}>
                  {stage === "creating" ? (
                    "Creating…"
                  ) : (
                    <>
                      <Sparkles aria-hidden="true" className="size-4.5" />
                      Generate questions
                    </>
                  )}
                </Button>
                <p className="text-center text-[13px] text-ink-3">
                  The clock starts only when you press Start.
                </p>
                <button
                  type="button"
                  onClick={startOver}
                  disabled={stage === "creating"}
                  className="cursor-pointer self-center text-[13px] font-medium text-accent underline-offset-4 hover:underline disabled:opacity-50"
                >
                  Use a different resume
                </button>
              </div>
            </>
          )}
        </motion.div>
      </AnimatePresence>
    </Card>
  );
}

function SourceToggle({
  value,
  onChange,
}: {
  value: "file" | "paste";
  onChange: (value: "file" | "paste") => void;
}) {
  const options = [
    { value: "file", label: "Upload file" },
    { value: "paste", label: "Paste text" },
  ] as const;
  return (
    <div
      role="radiogroup"
      aria-label="Resume source"
      className="grid grid-cols-2 gap-1 rounded-full bg-canvas p-1"
    >
      {options.map((option) => {
        const active = value === option.value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={`relative min-h-10 cursor-pointer rounded-full text-sm transition-colors duration-200 ${
              active ? "font-semibold text-ink" : "font-medium text-ink-2 hover:bg-white/65 hover:text-ink"
            }`}
          >
            {active && (
              <motion.span
                layoutId="source-toggle"
                className="absolute inset-0 rounded-full bg-surface shadow-[0_1px_2px_rgba(15,46,53,0.12)]"
                transition={{ type: "spring", stiffness: 500, damping: 38 }}
              />
            )}
            <span className="relative">{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/**
 * Drop a file or click to choose one. The real control is a visually hidden
 * <input type="file"> inside a <label>, so keyboard and screen-reader users
 * get the browser's own file picker — the drop zone is extra, not required.
 */
function FileDrop({ file, onPick }: { file: File | null; onPick: (file?: File) => void }) {
  const [dragging, setDragging] = useState(false);

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault(); // without this the browser opens the file instead
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        onPick(e.dataTransfer.files[0]);
      }}
      className={`group relative flex cursor-pointer flex-col items-center gap-2.5 rounded-[14px] border-[1.5px] border-dashed px-5 py-7 text-center transition-[background,border-color,transform] duration-200 ${
        dragging
          ? "scale-[1.01] border-accent bg-accent-soft"
          : "border-line-dashed bg-subtle hover:border-accent hover:bg-accent-soft"
      }`}
    >
      <input
        type="file"
        accept={RESUME_EXTENSIONS.join(",")}
        className="sr-only"
        onChange={(e) => {
          onPick(e.target.files?.[0]);
          e.target.value = ""; // choosing the same file again should still fire
        }}
      />
      <motion.span
        animate={dragging ? { y: -4 } : { y: 0 }}
        className="flex size-11 items-center justify-center rounded-full bg-accent-subtle text-accent transition-transform duration-250 group-hover:-translate-y-0.5"
      >
        {file ? (
          <FileText aria-hidden="true" className="size-5" />
        ) : (
          <Upload aria-hidden="true" className="size-5" />
        )}
      </motion.span>
      {file ? (
        <>
          <span className="max-w-full truncate font-semibold text-ink">{file.name}</span>
          <span className="tabular text-[13px] text-ink-3">
            {formatBytes(file.size)} · click or drop to choose another
          </span>
        </>
      ) : (
        <>
          <span className="font-semibold text-ink">
            Drop your resume here, or{" "}
            <span className="text-accent underline underline-offset-2">browse</span>
          </span>
          <span className="text-[13px] text-ink-3">PDF, DOCX or TXT, up to 2 MB</span>
        </>
      )}
    </label>
  );
}
