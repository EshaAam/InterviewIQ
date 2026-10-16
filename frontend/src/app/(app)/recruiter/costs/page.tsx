"use client";

import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { CircleDollarSign, Coins, ReceiptText, TriangleAlert } from "lucide-react";
import { describeError, getCosts, type CostSummary } from "@/lib/api";
import { shortId } from "@/lib/format";
import { BarFill, CountUp, EASE, Stagger, StaggerItem } from "@/components/motion";
import {
  Card,
  Chip,
  EmptyState,
  ErrorBanner,
  PageLoading,
  Shell,
  StatCard,
} from "@/components/ui";
import { PageHero } from "@/components/page-hero";

const COLUMNS =
  "grid grid-cols-[80px_90px_minmax(0,1fr)_140px_90px_90px_100px] items-center gap-3";

export default function CostsPage() {
  const [data, setData] = useState<CostSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCosts(25)
      .then((summary) => {
        if (!cancelled) setData(summary);
      })
      .catch((err) => {
        if (!cancelled) setError(describeError(err, "Could not load costs"));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <Shell>
        <ErrorBanner message={error} />
      </Shell>
    );
  }

  if (!data) return <PageLoading />;

  const pctUsed = Math.min(
    100,
    Math.round((data.tokens_today / Math.max(data.daily_token_budget, 1)) * 100),
  );
  const perCall = data.calls_today ? (data.spend_today / data.calls_today).toFixed(4) : "0.0000";

  return (
    <>
      <PageHero
        eyebrow="Recruiter"
        title="Costs"
        subtitle="One row per provider call, written whether it succeeded or not. The daily cap is enforced against this same ledger."
      />
      <Shell>
        <div className="flex flex-col gap-6">
          <Stagger className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StaggerItem className="flex">
              <StatCard
                label="Tokens today"
                icon={<Coins aria-hidden="true" className="size-4" />}
                value={<CountUp value={data.tokens_today} className="tabular" />}
                caption={`across all users · per-user cap ${data.daily_token_budget.toLocaleString()}`}
              />
            </StaggerItem>
            <StaggerItem className="flex">
              <StatCard
                label="Spend today"
                icon={<CircleDollarSign aria-hidden="true" className="size-4" />}
                value={`$${data.spend_today.toFixed(2)}`}
                caption={`${data.calls_today} calls`}
              />
            </StaggerItem>
            <StaggerItem className="flex">
              <StatCard
                label="Per call"
                icon={<ReceiptText aria-hidden="true" className="size-4" />}
                value={`$${perCall}`}
                caption="mean, today"
              />
            </StaggerItem>
            <StaggerItem className="flex">
              <StatCard
                label="Failed calls"
                icon={<TriangleAlert aria-hidden="true" className="size-4" />}
                value={String(data.failed_today)}
                caption="errors and open-circuit calls"
              />
            </StaggerItem>
          </Stagger>

          <Card className="flex flex-col gap-3 p-6">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-semibold">
                Today&apos;s tokens against one user&apos;s daily cap · resets at UTC midnight
              </span>
              <Chip tone={pctUsed >= 80 ? "warn" : "accent"}>{pctUsed}% of one cap</Chip>
            </div>
            <div className="h-3 w-full overflow-hidden rounded-full bg-track">
              <BarFill
                pct={pctUsed}
                className={`h-full rounded-full ${
                  pctUsed >= 80 ? "bg-linear-to-r from-[#e0a06a] to-warn" : "bg-linear-to-r from-accent to-glow"
                }`}
              />
            </div>
            <p className="text-sm text-ink-3">
              The cap is per user. A user past it can&apos;t submit a new resume or create a new
              interview (429) — the spend stops at the door, before anything is queued. Answering
              and finishing an interview already under way are never blocked.
            </p>
          </Card>

          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <div className="min-w-205">
                <div
                  className={`${COLUMNS} border-b border-line bg-subtle px-6 py-3 text-[11px] font-semibold tracking-[0.06em] text-ink-3 uppercase`}
                >
                  <span>Time</span>
                  <span>Session</span>
                  <span>Provider · model</span>
                  <span>Prompt / completion</span>
                  <span>Latency</span>
                  <span>Cost</span>
                  <span>Status</span>
                </div>

                {data.recent.length === 0 && (
                  <div className="p-6">
                    <EmptyState
                      icon={<ReceiptText aria-hidden="true" className="size-6" />}
                      title="No calls recorded yet"
                    />
                  </div>
                )}

                {data.recent.map((call, i) => (
                  <motion.div
                    key={call.id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: Math.min(i, 15) * 0.025, duration: 0.3, ease: EASE }}
                    className={`${COLUMNS} border-b border-line-soft px-6 py-3 text-[13px] transition-colors duration-150 last:border-b-0 hover:bg-accent-soft`}
                  >
                    <span className="tabular text-ink-3">
                      {new Date(call.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </span>
                    <span className="tabular font-mono text-xs text-ink-3">
                      {call.session_id ? shortId(call.session_id) : "—"}
                    </span>
                    <span className="truncate text-ink-2">
                      {call.provider} · {call.model}
                    </span>
                    <span className="tabular text-ink-2">
                      {call.prompt_tokens.toLocaleString()} / {call.completion_tokens.toLocaleString()}
                    </span>
                    <span className="tabular text-ink-2">{call.latency_ms.toLocaleString()} ms</span>
                    <span className="tabular font-semibold text-ink">
                      ${call.cost_estimate.toFixed(4)}
                    </span>
                    <span>
                      <Chip tone={call.status === "ok" ? "ok" : call.status === "cached" ? "info" : "bad"}>
                        {call.status}
                      </Chip>
                    </span>
                  </motion.div>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </Shell>
    </>
  );
}
