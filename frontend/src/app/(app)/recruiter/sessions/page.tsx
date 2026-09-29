"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiError, listSessions, type RecruiterSession, type SessionState } from "@/lib/api";
import { relativeTime, shortId } from "@/lib/format";
import { Card, PageHeading, Shell, StatusPill } from "@/components/ui";

const FILTERS: (SessionState | "All")[] = [
  "All",
  "NEEDS_HUMAN_REVIEW",
  "IN_PROGRESS",
  "EVALUATING",
  "COMPLETED",
  "FAILED",
  "EXPIRED",
];

export default function RecruiterSessionsPage() {
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("All");
  const [rows, setRows] = useState<RecruiterSession[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRows(null);
    listSessions({ state: filter === "All" ? undefined : filter, limit: 50 })
      .then((data) => {
        if (!cancelled) setRows(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Could not load sessions");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [filter]);

  return (
    <Shell>
      <div className="flex flex-col gap-4.5">
        <PageHeading
          title="Sessions"
          subtitle="Every interview, newest first. Filter by the state the session is sitting in."
        />

        <div className="flex flex-wrap gap-2">
          {FILTERS.map((option) => {
            const active = filter === option;
            return (
              <button
                key={option}
                onClick={() => setFilter(option)}
                className={`rounded-full px-3 py-1.5 text-[11px] font-medium transition-colors ${
                  active
                    ? "bg-accent text-ink-inv"
                    : "border border-line bg-surface text-ink-2 hover:bg-subtle"
                }`}
              >
                {option}
              </button>
            );
          })}
        </div>

        {error && (
          <p className="rounded-[10px] bg-bad-subtle px-4 py-3 text-[13px] text-bad">
            {error}
          </p>
        )}

        <Card className="overflow-hidden">
          <div className="grid grid-cols-[1fr_1fr_200px_140px_90px] items-center gap-4 border-b border-line bg-subtle px-5 py-3 text-[10px] font-semibold tracking-[0.7px] text-ink-3">
            <span>SESSION</span>
            <span>CANDIDATE</span>
            <span>STATE</span>
            <span>CREATED</span>
            <span />
          </div>

          {rows === null && (
            <p className="px-5 py-6 text-[13px] text-ink-3">Loading…</p>
          )}
          {rows?.length === 0 && (
            <p className="px-5 py-6 text-[13px] text-ink-3">
              No sessions in this state.
            </p>
          )}
          {rows?.map((row, i) => (
            <div
              key={row.id}
              className={`grid grid-cols-[1fr_1fr_200px_140px_90px] items-center gap-4 px-5 py-3 ${
                i < rows.length - 1 ? "border-b border-line" : ""
              }`}
            >
              <span className="tabular text-[13px] font-medium text-ink">
                {shortId(row.id)}
              </span>
              <span className="tabular text-xs text-ink-3">{shortId(row.user_id)}</span>
              <span>
                <StatusPill state={row.state} />
              </span>
              <span className="text-[13px] text-ink-3">
                {relativeTime(row.created_at)}
              </span>
              {row.state === "NEEDS_HUMAN_REVIEW" ? (
                <Link
                  href="/recruiter/review"
                  className="text-xs font-medium text-accent"
                >
                  Review →
                </Link>
              ) : (
                <span className="text-xs text-ink-3">—</span>
              )}
            </div>
          ))}
        </Card>

        <p className="text-xs text-ink-3">
          Scores and answer counts are not on this endpoint — open the review queue to
          see the answers a session flagged.
        </p>
      </div>
    </Shell>
  );
}
