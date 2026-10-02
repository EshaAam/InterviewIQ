"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  describeError,
  overrideEvaluation,
  reviewQueue,
  type EvaluationReview,
} from "@/lib/api";
import { AnimatePresence, motion } from "motion/react";
import { ArrowUpRight, CircleCheck, PartyPopper } from "lucide-react";
import { OverrideDialog } from "@/components/override-dialog";
import { EASE } from "@/components/motion";
import {
  Button,
  Card,
  Chip,
  EmptyState,
  ErrorBanner,
  PageHeading,
  ScoreBox,
  Shell,
  Skeleton,
} from "@/components/ui";

const PAGE_SIZE = 20;

type Queue = { items: EvaluationReview[]; total: number };

export default function ReviewQueuePage() {
  const [queue, setQueue] = useState<Queue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [overriding, setOverriding] = useState<EvaluationReview | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    let cancelled = false;
    reviewQueue({ limit: PAGE_SIZE })
      .then((page) => {
        if (!cancelled) setQueue(page);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err, "Could not load the queue"));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Resolved items leave the queue, so the next page starts at however many
   * are still loaded — not at "page × size", which would skip rows.
   */
  async function loadMore() {
    if (!queue) return;
    setLoadingMore(true);
    try {
      const page = await reviewQueue({ limit: PAGE_SIZE, offset: queue.items.length });
      setQueue((current) => {
        const known = new Set(current?.items.map((item) => item.id));
        return {
          items: [...(current?.items ?? []), ...page.items.filter((i) => !known.has(i.id))],
          total: page.total,
        };
      });
    } catch (err) {
      setError(describeError(err, "Could not load more"));
    } finally {
      setLoadingMore(false);
    }
  }

  /** Both "accept" and "set my own score" are the same call — only the number differs. */
  async function resolve(evaluation: EvaluationReview, score: number, note: string | null) {
    await overrideEvaluation(evaluation.id, score, note);
    // Filter it out locally; refetching would be a round trip to confirm our own action.
    setQueue((current) =>
      current && {
        items: current.items.filter((item) => item.id !== evaluation.id),
        total: current.total - 1,
      },
    );
    setOverriding(null);
  }

  const [head, ...rest] = queue?.items ?? [];

  return (
    <Shell width="medium">
      <div className="flex flex-col gap-6">
        <PageHeading
          title="Review queue"
          subtitle="Answers where the rule-based pass and the model pass disagreed past threshold. Nothing here has been auto-scored."
          actions={queue ? <Chip tone="warn">{queue.total} waiting</Chip> : undefined}
        />

        {error && <ErrorBanner message={error} />}

        {queue === null && !error && (
          <div className="flex flex-col gap-3">
            <span className="sr-only" role="status">
              Loading the queue…
            </span>
            <Skeleton className="h-72 w-full rounded-card" />
            <Skeleton className="h-16 w-full rounded-row" />
            <Skeleton className="h-16 w-full rounded-row" />
          </div>
        )}
        {queue?.items.length === 0 && (
          <EmptyState
            icon={<PartyPopper aria-hidden="true" className="size-6" />}
            title="All clear"
          >
            Nothing is waiting on a human right now.
          </EmptyState>
        )}

        <AnimatePresence mode="popLayout" initial={false}>
          {head && (
            <motion.div
              key={head.id}
              layout
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, x: 60, transition: { duration: 0.25 } }}
              transition={{ duration: 0.4, ease: EASE }}
            >
              <ExpandedReview
                item={head}
                onAccept={() =>
                  resolve(head, head.final_score, null).catch((err) =>
                    setError(describeError(err, "Could not save the score")),
                  )
                }
                onOverride={() => setOverriding(head)}
              />
            </motion.div>
          )}

          {rest.map((item) => (
            <motion.div
              key={item.id}
              layout
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.3, ease: EASE }}
            >
              <Link
                href={`/recruiter/sessions/${item.session_id}`}
                className="group flex items-center gap-3 rounded-row border border-line bg-surface px-5 py-4 shadow-card transition-[transform,box-shadow,border-color] duration-250 ease-out-soft hover:-translate-y-0.5 hover:border-accent-mid hover:shadow-lift"
              >
                <Chip tone="accent">{item.topic}</Chip>
                <span className="min-w-0 flex-1 truncate text-sm text-ink-2">
                  {item.question_text}
                </span>
                <span className="hidden truncate text-xs text-ink-3 sm:inline">
                  {item.candidate_email}
                </span>
                <span className="tabular shrink-0 text-xs font-semibold text-ink-3">
                  {item.deterministic_score.toFixed(2)} vs {item.final_score.toFixed(2)}
                </span>
                <ArrowUpRight
                  aria-hidden="true"
                  className="size-4 shrink-0 text-accent transition-transform duration-200 group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
                />
              </Link>
            </motion.div>
          ))}
        </AnimatePresence>

        {queue && queue.items.length < queue.total && (
          <div className="flex justify-center">
            <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
              {loadingMore ? "Loading…" : `Load more (${queue.total - queue.items.length} not shown)`}
            </Button>
          </div>
        )}
      </div>

      <AnimatePresence>
        {overriding && (
          <OverrideDialog
            item={overriding}
            onCancel={() => setOverriding(null)}
            onSave={(score, note) => resolve(overriding, score, note)}
          />
        )}
      </AnimatePresence>
    </Shell>
  );
}

function ExpandedReview({
  item,
  onAccept,
  onOverride,
}: {
  item: EvaluationReview;
  onAccept: () => void;
  onOverride: () => void;
}) {
  // final = (model + rule) / 2, so the model pass sits twice as far from the
  // rule pass as the final score does. That full distance is what was
  // compared against the divergence threshold.
  const delta = 2 * Math.abs(item.final_score - item.deterministic_score);

  return (
    <Card className="flex flex-col gap-5 border-warn-line p-6 shadow-[0_0_0_4px_var(--color-warn-subtle)] sm:p-7">
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone="accent">{item.topic}</Chip>
        <Chip>{item.run_count} runs</Chip>
        <Chip tone="warn">confidence {item.confidence.toFixed(2)}</Chip>
        <span className="ml-auto flex items-center gap-3 text-sm text-ink-3">
          <span className="truncate">{item.candidate_email}</span>
          <Link
            href={`/recruiter/sessions/${item.session_id}`}
            className="flex shrink-0 items-center gap-1 font-semibold text-accent hover:text-brand"
          >
            Open session
            <ArrowUpRight aria-hidden="true" className="size-4" />
          </Link>
        </span>
      </div>

      <h2 className="font-display text-xl leading-snug font-semibold">{item.question_text}</h2>

      <div className="rounded-[14px] border border-line-soft bg-field px-4 py-3.5 text-[15px] leading-relaxed whitespace-pre-wrap">
        {item.answer_text}
      </div>

      <div className="flex flex-wrap gap-3">
        <ScoreBox
          label="Rule-based pass"
          value={item.deterministic_score.toFixed(2)}
          caption="deterministic, concept coverage"
          tone="text-bad"
        />
        <ScoreBox
          label="Proposed final"
          value={item.final_score.toFixed(2)}
          caption={`reconciled over ${item.run_count} runs`}
          tone="text-ink"
        />
        <ScoreBox
          label="Confidence"
          value={item.confidence.toFixed(2)}
          caption="held back for review"
          tone="text-warn"
        />
      </div>

      <p className="text-sm text-ink-3">
        The passes are <span className="tabular font-semibold text-ink">{delta.toFixed(2)}</span>{" "}
        apart — this was queued instead of averaged.
      </p>

      <div className="flex flex-wrap items-center justify-end gap-3 border-t border-line-soft pt-5">
        <Button variant="secondary" onClick={onAccept}>
          <CircleCheck aria-hidden="true" className="size-4" />
          Accept {item.final_score.toFixed(2)}
        </Button>
        <Button onClick={onOverride}>Set my own score</Button>
      </div>
    </Card>
  );
}
