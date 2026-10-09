"use client";

import { use, useEffect, useState } from "react";
import { AnimatePresence } from "motion/react";
import { CircleCheck, ClipboardPaste, Clock, Flag, Gauge, Keyboard, Mic, Users } from "lucide-react";
import {
  describeError,
  getRecruiterSession,
  overrideEvaluation,
  type AnswerDetail,
  type EvaluationDetail,
  type QuestionDetail,
  type RecruiterSessionDetail,
} from "@/lib/api";
import { duration, relativeTime, sessionName, toHundred } from "@/lib/format";
import { DownloadPdfButton } from "@/components/download-pdf-button";
import { OverrideDialog } from "@/components/override-dialog";
import { Stagger, StaggerItem } from "@/components/motion";
import {
  CitedSources,
  BackLink,
  Button,
  Card,
  Chip,
  ErrorBanner,
  IntegrityBadge,
  Notice,
  PageHeading,
  PageLoading,
  ScoreBar,
  ScoreBox,
  Shell,
  StatCard,
  StatusPill,
} from "@/components/ui";

type Overriding = { evaluation: EvaluationDetail; topic: string };

export default function RecruiterSessionDetailPage({
  params,
}: {
  params: Promise<{ sessionId: string }>;
}) {
  const { sessionId } = use(params);
  const [detail, setDetail] = useState<RecruiterSessionDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overriding, setOverriding] = useState<Overriding | null>(null);
  // Bumped after an override to fetch the session again.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getRecruiterSession(sessionId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err, "Could not load this session"));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, version]);

  /**
   * Unlike the review queue, this page *refetches* after an override: the
   * server has just rebuilt the report and may have moved the session to
   * COMPLETED, and those are its numbers to compute, not ours.
   */
  async function save(evaluationId: string, score: number, note: string | null) {
    await overrideEvaluation(evaluationId, score, note);
    setOverriding(null);
    setVersion((v) => v + 1);
  }

  if (error && !detail) {
    return (
      <Shell width="medium">
        <div className="flex flex-col gap-4">
          <BackLink href="/recruiter/sessions">All sessions</BackLink>
          <ErrorBanner message={error} />
        </div>
      </Shell>
    );
  }
  if (!detail) return <PageLoading />;

  const evaluations = detail.questions.flatMap((q) =>
    q.answers.flatMap((a) => (a.evaluation ? [a.evaluation] : [])),
  );
  const flagged = evaluations.filter((e) => e.needs_review).length;
  const answered = detail.questions.filter((q) => q.answers.length > 0).length;
  const topics = detail.report
    ? Object.entries(detail.report.per_topic).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <Shell>
      <div className="flex flex-col gap-6">
        <BackLink href="/recruiter/sessions">All sessions</BackLink>

        <PageHeading
          size="md"
          title={detail.candidate_email}
          subtitle={`Session ${sessionName(detail.id)} · created ${relativeTime(detail.created_at)} · ${detail.questions.length} questions`}
          actions={
            <>
              {detail.integrity_flag && <IntegrityBadge />}
              <StatusPill state={detail.state} />
              {detail.report && <DownloadPdfButton sessionId={detail.id} asRecruiter />}
            </>
          }
        />

        {error && <ErrorBanner message={error} />}
        {detail.failure_reason && (
          <Notice tone="bad" role="alert" title="This session failed">
            {detail.failure_reason}
          </Notice>
        )}
        {detail.resume_integrity.length > 0 && (
          /* The résumé tried to instruct the AI that wrote these questions.
             Advisory: the text was fenced off as data, so this says what was
             attempted, not that it worked. */
          <Notice tone="warn" title="Résumé — advisory">
            {detail.resume_integrity.map((signal) => (
              <span key={signal.code} className="block">
                {signal.detail}
              </span>
            ))}
            <span className="mt-1 block text-xs opacity-80">
              The résumé was passed to the AI as data, never as instructions. Check the
              questions below look like a normal interview.
            </span>
          </Notice>
        )}

        <div className="flex flex-wrap gap-4">
          <StatCard
            label="Overall score"
            icon={<Gauge aria-hidden="true" className="size-4" />}
            value={detail.report ? `${toHundred(detail.report.overall)}/100` : "—"}
            caption={
              detail.report?.human_reviewed
                ? "includes recruiter overrides"
                : detail.report
                  ? "as graded"
                  : "no report yet"
            }
          />
          <StatCard
            label="Answered"
            icon={<Users aria-hidden="true" className="size-4" />}
            value={`${answered}/${detail.questions.length}`}
            caption="questions with an answer"
          />
          <StatCard
            label="Waiting on review"
            icon={<Flag aria-hidden="true" className="size-4" />}
            value={String(flagged)}
            caption={flagged === 0 ? "nothing flagged" : "answers flagged below"}
          />
        </div>

        {topics.length > 0 && (
          <Card className="flex flex-col gap-5 p-7">
            <h2 className="text-lg font-semibold">Score by topic</h2>
            <div className="grid gap-5 md:grid-cols-2">
              {topics.map(([topic, score], i) => (
                <ScoreBar key={topic} topic={topic} score={score} delay={i * 0.06} />
              ))}
            </div>
          </Card>
        )}

        {detail.jd_gaps.length > 0 && (
          /* What the questions were aimed at. Shown as stored at generation
             time, not recomputed, so this stays an accurate record of what
             this interview actually targeted. */
          <Card as="section" aria-labelledby="jd-gaps" className="flex flex-col gap-3 p-6">
            <h2 id="jd-gaps" className="text-lg font-semibold">
              Targeted from the job description
            </h2>
            <p className="text-[13px] text-ink-3">
              Requirements the resume did not evidence. Questions were weighted towards
              these rather than towards skills already on the page.
            </p>
            <ul className="flex flex-col gap-2">
              {detail.jd_gaps.map((gap) => (
                <li key={gap} className="flex items-baseline gap-2 text-[14px]">
                  <span aria-hidden="true" className="text-warn">
                    &bull;
                  </span>
                  <span className="text-ink-2">{gap}</span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        <Stagger className="flex flex-col gap-4">
          {detail.questions.map((question) => (
            <StaggerItem key={question.id}>
              <QuestionCard
                question={question}
                onOverride={(evaluation) => setOverriding({ evaluation, topic: question.topic })}
                onAccept={(evaluation) =>
                  save(evaluation.id, evaluation.final_score, null).catch((err) =>
                    setError(describeError(err, "Could not save the score")),
                  )
                }
              />
            </StaggerItem>
          ))}
        </Stagger>
      </div>

      <AnimatePresence>
        {overriding && (
          <OverrideDialog
            item={{
              topic: overriding.topic,
              final_score: overriding.evaluation.final_score,
              deterministic_score: overriding.evaluation.deterministic_score,
            }}
            onCancel={() => setOverriding(null)}
            onSave={(score, note) => save(overriding.evaluation.id, score, note)}
          />
        )}
      </AnimatePresence>
    </Shell>
  );
}

function QuestionCard({
  question,
  onOverride,
  onAccept,
}: {
  question: QuestionDetail;
  onOverride: (evaluation: EvaluationDetail) => void;
  onAccept: (evaluation: EvaluationDetail) => void;
}) {
  const flagged = question.answers.some((a) => a.evaluation?.needs_review);
  return (
    <Card
      as="article"
      className={`flex flex-col gap-4 p-6 sm:p-7 ${flagged ? "border-warn-line shadow-[0_0_0_4px_var(--color-warn-subtle)]" : ""}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="tabular flex size-7 items-center justify-center rounded-lg bg-canvas text-xs font-bold text-ink-2">
          Q{question.ordinal + 1}
        </span>
        <Chip tone="accent">{question.topic}</Chip>
        <Chip>{question.difficulty}</Chip>
      </div>
      <h2 className="font-display text-xl leading-snug font-semibold">{question.text}</h2>

      <div className="flex flex-wrap items-center gap-1.5">
        <span className="mr-1 text-xs font-semibold tracking-[0.04em] text-ink-3 uppercase">
          Expected
        </span>
        {question.expected_concepts.map((concept) => (
          <span
            key={concept}
            className="rounded-md border border-line-soft bg-subtle px-2 py-0.5 text-[13px] text-ink-2"
          >
            {concept}
          </span>
        ))}
      </div>

      {/* Where the answer key came from. A recruiter defending a score needs to
          be able to trace it to a source in one click. */}
      <CitedSources sources={question.sources} grounded={question.grounded} />

      {question.answers.length === 0 && <p className="text-sm text-ink-3">Not answered.</p>}
      {question.answers.map((answer) => (
        <AnswerBlock key={answer.id} answer={answer} onOverride={onOverride} onAccept={onAccept} />
      ))}
    </Card>
  );
}

function AnswerBlock({
  answer,
  onOverride,
  onAccept,
}: {
  answer: AnswerDetail;
  onOverride: (evaluation: EvaluationDetail) => void;
  onAccept: (evaluation: EvaluationDetail) => void;
}) {
  const evaluation = answer.evaluation;

  return (
    <div className="flex flex-col gap-4 border-t border-line-soft pt-4">
      <div className="rounded-[14px] border border-line-soft bg-field px-4 py-3.5 text-[15px] leading-relaxed whitespace-pre-wrap text-ink">
        {answer.text}
      </div>

      {/* Raw typing telemetry; the integrity box below interprets it. */}
      <div className="tabular flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-ink-3">
        <span className="flex items-center gap-1.5">
          <Clock aria-hidden="true" className="size-3.5" />
          {answer.time_taken_ms != null ? duration(answer.time_taken_ms) : "—"} to answer
        </span>
        <span
          className={`flex items-center gap-1.5 ${answer.paste_events > 0 ? "font-semibold text-warn" : ""}`}
        >
          <ClipboardPaste aria-hidden="true" className="size-3.5" />
          {answer.paste_events} paste{answer.paste_events === 1 ? "" : "s"}
        </span>
        <span className="flex items-center gap-1.5">
          <Keyboard aria-hidden="true" className="size-3.5" />
          {answer.keystroke_count ?? "—"} keystrokes
        </span>
        {answer.dictated_chars > 0 && (
          // Measured by the server against its own transcripts, so the typing
          // signals already discount it.
          <span className="flex items-center gap-1.5">
            <Mic aria-hidden="true" className="size-3.5" />
            {answer.dictated_chars.toLocaleString()} of {answer.text.length.toLocaleString()}{" "}
            chars spoken
          </span>
        )}
      </div>

      {answer.integrity.length > 0 && (
        <Notice tone="warn" title="Integrity — advisory">
          {answer.integrity.map((signal) => (
            <span key={signal.code} className="block">
              {signal.detail}
            </span>
          ))}
          <span className="mt-1 block text-xs opacity-80">
            From browser-reported typing data and the answer&apos;s own text. A reason to read
            closely, not a finding — it has not changed the score.
          </span>
        </Notice>
      )}

      {!evaluation && <p className="text-sm text-ink-3">Not graded yet.</p>}

      {evaluation && (
        <>
          <div className="flex flex-wrap gap-3">
            <ScoreBox
              label="Rule-based pass"
              value={evaluation.deterministic_score.toFixed(2)}
              caption="concept coverage"
              tone="text-ink"
            />
            <ScoreBox
              label="Final"
              value={evaluation.final_score.toFixed(2)}
              caption={
                evaluation.overridden_by_id
                  ? "set by a recruiter"
                  : `reconciled over ${evaluation.run_count} run${evaluation.run_count === 1 ? "" : "s"}`
              }
              tone={evaluation.needs_review ? "text-warn" : "text-accent-strong"}
            />
            <ScoreBox
              label="Confidence"
              value={evaluation.confidence.toFixed(2)}
              caption={evaluation.needs_review ? "held back for review" : "auto-scored"}
              tone="text-ink"
            />
          </div>

          {Object.keys(evaluation.llm_scores).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(evaluation.llm_scores).map(([axis, score]) => (
                <span
                  key={axis}
                  className="tabular rounded-full border border-line px-2.5 py-0.5 text-xs text-ink-2"
                >
                  model {axis} <span className="font-semibold text-ink">{score.toFixed(2)}</span>
                </span>
              ))}
            </div>
          )}

          {evaluation.overridden_by_id && (
            <Notice tone="info">
              Overridden by a recruiter
              {evaluation.override_note ? ` — “${evaluation.override_note}”` : "."}
            </Notice>
          )}

          <div className="flex flex-wrap items-center justify-end gap-2.5">
            {evaluation.needs_review ? (
              <>
                <Chip tone="warn">needs review</Chip>
                <Button variant="secondary" onClick={() => onAccept(evaluation)}>
                  <CircleCheck aria-hidden="true" className="size-4" />
                  Accept {evaluation.final_score.toFixed(2)}
                </Button>
                <Button onClick={() => onOverride(evaluation)}>Set my own score</Button>
              </>
            ) : (
              <Button variant="ghost" size="sm" onClick={() => onOverride(evaluation)}>
                Adjust score
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
