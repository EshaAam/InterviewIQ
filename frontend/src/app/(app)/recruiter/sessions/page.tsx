"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "motion/react";
import { ChevronRight, Inbox } from "lucide-react";
import { describeError, listSessions, type RecruiterSession, type SessionState } from "@/lib/api";
import { relativeTime, sessionName } from "@/lib/format";
import { Stagger, StaggerItem } from "@/components/motion";
import {
  Card,
  EmptyState,
  ErrorBanner,
  IntegrityBadge,
  PageHeading,
  Shell,
  Skeleton,
  StatusPill,
} from "@/components/ui";

// PARSING and GENERATING_QS are left out on purpose: the worker passes through
// both inside one transaction, so no session is ever *seen* sitting in them.
// CREATED is where a session waits if no worker picks up its job.
const FILTERS: (SessionState | "All")[] = [
  "All",
  "NEEDS_HUMAN_REVIEW",
  "CREATED",
  "READY",
  "IN_PROGRESS",
  "EVALUATING",
  "COMPLETED",
  "FAILED",
  "EXPIRED",
];

type Filter = (typeof FILTERS)[number];
type Result = { filter: Filter; rows: RecruiterSession[]; error: string | null };

const COLUMNS = "md:grid md:grid-cols-[110px_minmax(0,1fr)_200px_110px_24px] md:items-center md:gap-4";

export default function RecruiterSessionsPage() {
  const [filter, setFilter] = useState<Filter>("All");
  // Each result remembers which filter it was fetched for. When the filter
  // changes, the old result no longer matches, so the page shows "Loading…"
  // without having to reset anything — and a stale error disappears with it.
  const [result, setResult] = useState<Result | null>(null);

  useEffect(() => {
    let cancelled = false;
    listSessions({ state: filter === "All" ? undefined : filter, limit: 50 })
      .then((rows) => {
        if (!cancelled) setResult({ filter, rows, error: null });
      })
      .catch((err) => {
        if (!cancelled) {
          setResult({ filter, rows: [], error: describeError(err, "Could not load sessions") });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [filter]);

  const current = result?.filter === filter ? result : null;
  const rows = current?.rows ?? null; // null = loading, [] = empty
  const error = current?.error ?? null;

  return (
    <Shell>
      <div className="flex flex-col gap-6">
        <PageHeading
          title="Sessions"
          subtitle="Every interview, newest first. Filter by the state a session is sitting in, and open one to see its answers."
        />

        <div role="group" aria-label="Filter by state" className="flex flex-wrap gap-2">
          {FILTERS.map((option) => {
            const active = filter === option;
            return (
              <button
                key={option}
                onClick={() => setFilter(option)}
                aria-pressed={active}
                className={`relative cursor-pointer rounded-full border px-3.5 py-1.5 text-xs font-semibold tracking-[0.02em] transition-colors duration-200 ${
                  active
                    ? "border-transparent text-ink-inv"
                    : "border-line bg-surface text-ink-2 hover:border-accent-mid hover:text-ink"
                }`}
              >
                {active && (
                  <motion.span
                    layoutId="state-filter"
                    className="absolute inset-0 rounded-full bg-brand"
                    transition={{ type: "spring", stiffness: 420, damping: 34 }}
                  />
                )}
                <span className="relative">{option}</span>
              </button>
            );
          })}
        </div>

        {error && <ErrorBanner message={error} />}

        <Card className="overflow-hidden">
          <div
            className={`hidden border-b border-line bg-subtle px-6 py-3 text-[11px] font-semibold tracking-[0.06em] text-ink-3 uppercase ${COLUMNS}`}
          >
            <span>Session</span>
            <span>Candidate</span>
            <span>State</span>
            <span>Created</span>
            <span />
          </div>

          {rows === null && (
            <div className="flex flex-col gap-2 p-4">
              <span className="sr-only" role="status">
                Loading sessions…
              </span>
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          )}
          {rows?.length === 0 && !error && (
            <div className="p-6">
              <EmptyState icon={<Inbox aria-hidden="true" className="size-6" />} title="No sessions here">
                Nothing is sitting in {filter === "All" ? "any state" : filter} right now.
              </EmptyState>
            </div>
          )}
          {rows && rows.length > 0 && (
            <Stagger key={filter} className="divide-y divide-line-soft">
              {rows.map((row) => (
                <StaggerItem key={row.id}>
                  {/* The whole row is the link: a table you click through should
                      not make you aim for a small "open" word at the end. */}
                  <Link
                    href={`/recruiter/sessions/${row.id}`}
                    className={`group flex flex-wrap items-center gap-x-4 gap-y-2 px-6 py-4 transition-colors duration-200 hover:bg-accent-soft ${COLUMNS}`}
                  >
                    <span className="tabular font-semibold text-ink">{sessionName(row.id)}</span>
                    <span className="flex min-w-0 items-center gap-2">
                      <span className="truncate text-ink-2">{row.candidate_email}</span>
                      {row.integrity_flag && <IntegrityBadge />}
                    </span>
                    <span>
                      <StatusPill state={row.state} />
                    </span>
                    <span className="text-sm text-ink-3">{relativeTime(row.created_at)}</span>
                    <ChevronRight
                      aria-hidden="true"
                      className="ml-auto size-4 text-accent transition-transform duration-200 group-hover:translate-x-1"
                    />
                  </Link>
                </StaggerItem>
              ))}
            </Stagger>
          )}
        </Card>
      </div>
    </Shell>
  );
}
