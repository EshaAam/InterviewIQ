"use client";

import { use, useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, Loader2, Target, Trophy } from "lucide-react";
import {
  describeError,
  getReport,
  getSession,
  type Report,
  type Session,
} from "@/lib/api";
import { humanWhen, sessionName, toHundred } from "@/lib/format";
import { isAbort, pollUntil, PollTimeout } from "@/lib/poll";
import { DownloadPdfButton } from "@/components/download-pdf-button";
import { CountUp, EASE, ScoreRing, Stagger, StaggerItem } from "@/components/motion";
import {
  BackLink,
  buttonClass,
  Card,
  ErrorBanner,
  Notice,
  PageHeading,
  PageLoading,
  ScoreBar,
  Shell,
  StatusPill,
} from "@/components/ui";

const REPORTED = new Set(["COMPLETED", "NEEDS_HUMAN_REVIEW"]);

export default function ReportPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const [session, setSession] = useState<Session | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    // Ask for the session first: its state says whether a report can exist
    // yet, so we never treat "still grading" as a 404 error.
    (async () => {
      let latest = await getSession(sessionId);
      setSession(latest);
      if (latest.state === "EVALUATING") {
        latest = await pollUntil(
          () => getSession(sessionId),
          (s) => s.state !== "EVALUATING",
          { signal: controller.signal, timeoutMs: 10 * 60_000 },
        );
        setSession(latest);
      }
      if (REPORTED.has(latest.state)) {
        setReport(await getReport(sessionId));
      }
    })().catch((err) => {
      if (isAbort(err)) return;
      if (err instanceof PollTimeout) setSlow(true);
      else setError(describeError(err, "Could not load the report"));
    });

    return () => controller.abort();
  }, [sessionId]);

  if (error) {
    return (
      <Shell width="narrow">
        <div className="flex flex-col gap-4">
          <BackLink href="/interview">My interviews</BackLink>
          <ErrorBanner message={error} />
        </div>
      </Shell>
    );
  }

  if (!session) return <PageLoading />;

  if (session.state === "EVALUATING") {
    return (
      <Shell width="narrow">
        <Card className="flex flex-col items-start gap-3 p-8">
          <StatusPill state={session.state} />
          <h1 className="font-display text-[28px] font-bold tracking-[-0.02em]">
            Your report is on its way
          </h1>
          <p className="flex items-center gap-2 text-ink-2">
            {!slow && <Loader2 aria-hidden="true" className="size-4 animate-spin text-accent" />}
            {slow
              ? "Grading is taking longer than usual. Your answers are saved — reload this page later to see the result."
              : "Your answers are being graded. This page will show the report as soon as it's ready."}
          </p>
        </Card>
      </Shell>
    );
  }

  if (!REPORTED.has(session.state)) {
    return (
      <Shell width="narrow">
        <Card className="flex flex-col items-start gap-3 p-8">
          <StatusPill state={session.state} />
          <h1 className="font-display text-[28px] font-bold tracking-[-0.02em]">No report yet</h1>
          <p className="text-ink-2">
            {session.state === "EXPIRED" || session.state === "FAILED"
              ? "This interview ended without a report."
              : "This interview hasn't been finished yet, so there is no report."}
          </p>
          <Link href={`/interview/${sessionId}`} className={buttonClass("primary")}>
            Go to the interview
          </Link>
        </Card>
      </Shell>
    );
  }

  if (!report) return <PageLoading />;

  const topics = Object.entries(report.per_topic).sort((a, b) => b[1] - a[1]);
  const strongest = topics[0]?.[0];
  const overall = toHundred(report.overall);
  const gaps = report.gaps
    .map((topic) => [topic, report.per_topic[topic] ?? 0] as const)
    .sort((a, b) => a[1] - b[1]);
  const finished = session.updated_at ? `, finished ${humanWhen(session.updated_at)}` : "";

  return (
    <Shell>
      <div className="flex flex-col gap-6">
        <BackLink href="/interview">My interviews</BackLink>

        <PageHeading
          title="Interview report"
          subtitle={`Session ${sessionName(sessionId)}, ${session.total_questions} question${session.total_questions === 1 ? "" : "s"}${finished}`}
          actions={
            <>
              <StatusPill state={session.state} />
              <DownloadPdfButton sessionId={sessionId} />
            </>
          }
        />

        {session.state === "NEEDS_HUMAN_REVIEW" && (
          <Notice tone="warn" role="status" title="A recruiter is checking one of your answers">
            The two grading passes disagreed, so a person is reading it rather than
            averaging two different scores. Your score may change once they&apos;re done.
          </Notice>
        )}

        {session.state === "COMPLETED" && report.human_reviewed && (
          <Notice tone="info" title="Reviewed by a recruiter">
            A person read the answers the graders disagreed on and set their scores. The
            numbers below include those decisions.
          </Notice>
        )}

        <motion.section
          aria-labelledby="overall"
          initial={{ opacity: 0, y: 16, scale: 0.99 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.6, ease: EASE }}
          className="surface-hero relative flex flex-wrap items-center gap-10 overflow-hidden rounded-[24px] p-7 sm:p-9"
        >
          {/* A slow drifting glow behind the numbers. */}
          <motion.span
            aria-hidden="true"
            className="pointer-events-none absolute -top-24 -right-16 size-80 rounded-full bg-glow/20 blur-3xl"
            animate={{ x: [0, -30, 0], y: [0, 20, 0] }}
            transition={{ duration: 12, repeat: Infinity, ease: "easeInOut" }}
          />
          <ScoreRing pct={overall} />
          <div className="relative flex min-w-[280px] flex-1 flex-col gap-5">
            <div>
              <h2 id="overall" className="font-display text-[26px] font-bold">
                Overall score
              </h2>
              <p className="mt-1 text-base text-ink-on-dark">
                Averaged across {session.answered} answer{session.answered === 1 ? "" : "s"},
                each graded twice.
              </p>
            </div>
            <Stagger className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <HeroStat value={<CountUp value={session.answered} />} label="Answers graded" />
              <HeroStat value={<CountUp value={topics.length} />} label="Topics from your resume" />
              <HeroStat value={strongest ?? "—"} label="Strongest topic" />
            </Stagger>
          </div>
        </motion.section>

        <div className="flex flex-col gap-6 lg:flex-row lg:items-start">
          <Card as="section" aria-labelledby="topics" className="flex min-w-0 flex-1 flex-col gap-[22px] p-7">
            <div className="flex items-baseline justify-between">
              <h2 id="topics" className="text-lg font-semibold">
                Score by topic
              </h2>
              <span className="text-[13px] text-ink-3">Strongest first</span>
            </div>
            {topics.length === 0 && (
              <span className="text-ink-3">No per-topic scores recorded.</span>
            )}
            {topics.map(([topic, score], i) => (
              <ScoreBar key={topic} topic={topic} score={score} delay={0.1 + i * 0.08} />
            ))}
          </Card>

          <div className="flex w-full flex-col gap-6 lg:w-[420px] lg:shrink-0">
            <Card as="section" aria-labelledby="gaps" className="flex flex-col gap-4 p-7">
              <h2 id="gaps" className="flex items-center gap-2 text-lg font-semibold">
                <Target aria-hidden="true" className="size-5 text-warn" />
                Topics to work on
              </h2>
              {gaps.length === 0 ? (
                <p className="text-ink-3">Nothing scored below 50. Nice work.</p>
              ) : (
                <>
                  <Stagger as="ul" className="flex flex-col gap-2.5">
                    {gaps.map(([topic, score]) => (
                      <StaggerItem
                        as="li"
                        key={topic}
                        className="flex items-center justify-between rounded-[12px] bg-warn-subtle px-3.5 py-3 transition-[background,transform] duration-200 hover:translate-x-0.5 hover:bg-warn-hover"
                      >
                        <span className="font-semibold text-warn-deep">{topic}</span>
                        <span className="tabular text-[13px] text-warn">
                          {toHundred(score)}/100
                        </span>
                      </StaggerItem>
                    ))}
                  </Stagger>
                  <Link href="/interview" className={buttonClass("primary", "md", "group w-full")}>
                    Practise these again
                    <ArrowRight
                      aria-hidden="true"
                      className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
                    />
                  </Link>
                </>
              )}
            </Card>

            <Card as="section" aria-labelledby="strengths" className="flex flex-col gap-3 p-7">
              <h2 id="strengths" className="flex items-center gap-2 text-lg font-semibold">
                <Trophy aria-hidden="true" className="size-5 text-ok" />
                Strengths
              </h2>
              {report.strengths.length === 0 ? (
                <p className="text-ink-3">None yet. Topics you answer well will appear here.</p>
              ) : (
                <Stagger as="ul" className="flex flex-col gap-2.5">
                  {report.strengths.map((topic) => (
                    <StaggerItem
                      as="li"
                      key={topic}
                      className="flex items-center justify-between rounded-[12px] bg-ok-subtle px-3.5 py-3 transition-transform duration-200 hover:translate-x-0.5"
                    >
                      <span className="font-semibold text-ok">{topic}</span>
                      <span className="tabular text-[13px] text-ok">
                        {toHundred(report.per_topic[topic] ?? 0)}/100
                      </span>
                    </StaggerItem>
                  ))}
                </Stagger>
              )}
            </Card>
          </div>
        </div>
      </div>
    </Shell>
  );
}

function HeroStat({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <StaggerItem className="cursor-default rounded-[14px] bg-brand-3 px-4 py-3.5 transition-[background,transform] duration-250 ease-out-soft hover:-translate-y-0.5 hover:bg-brand-4">
      <div className="tabular truncate font-display text-[26px] font-bold">{value}</div>
      <div className="text-[13px] text-ink-on-dark">{label}</div>
    </StaggerItem>
  );
}
