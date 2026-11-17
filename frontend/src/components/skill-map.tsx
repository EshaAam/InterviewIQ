"use client";

import Link from "next/link";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  CircleDashed,
  Minus,
  X,
} from "lucide-react";
import type {
  CitedSource,
  ConceptEvidence,
  QuestionEvidence,
  SkillEvidence,
  SkillMap,
  SkillStatus,
} from "@/lib/api";
import { humanWhen, toHundred } from "@/lib/format";
import { BarFill } from "@/components/motion";
import { buttonClass, Card, Chip, EmptyState, type Tone } from "@/components/ui";

/**
 * The skill evidence map: every skill a candidate has been graded on across
 * all their interviews, grouped by where it stands now, plus the résumé skills
 * no interview has asked about.
 *
 * One component for both readers. The candidate's copy links each skill to
 * their own report and offers another interview; the recruiter's links to the
 * session review screen and offers nothing, because a recruiter cannot start
 * an interview on someone's behalf.
 */

const STATUS: Record<
  SkillStatus,
  { label: string; tone: Tone; bar: string; title: string; blurb: string }
> = {
  weak: {
    label: "Weak",
    tone: "warn",
    bar: "bg-warn",
    title: "Needs work",
    blurb: "Scored below 50 the last time it was asked.",
  },
  developing: {
    label: "Developing",
    tone: "info",
    bar: "bg-info",
    title: "Developing",
    blurb: "Between 50 and 70: partly there, with concepts still missing.",
  },
  demonstrated: {
    label: "Demonstrated",
    tone: "ok",
    bar: "bg-ok",
    title: "Demonstrated",
    blurb: "Scored 70 or more the last time it was asked.",
  },
};

/** Weakest first — the same order the server sends skills in. */
const ORDER: SkillStatus[] = ["weak", "developing", "demonstrated"];

/** A concept at or above this is covered; the grader reports 0, 0.5 or 1. */
const COVERED = 1;
const PARTLY = 0.5;

export function countByStatus(map: SkillMap): Record<SkillStatus, number> {
  const counts: Record<SkillStatus, number> = { weak: 0, developing: 0, demonstrated: 0 };
  for (const skill of map.skills) counts[skill.status] += 1;
  return counts;
}

export function SkillMapView({
  map,
  forRecruiter = false,
}: {
  map: SkillMap;
  forRecruiter?: boolean;
}) {
  if (map.skills.length === 0 && map.not_assessed.length === 0) {
    return (
      <EmptyState
        icon={<CircleDashed aria-hidden="true" className="size-6" />}
        title="Nothing to map yet"
        action={
          !forRecruiter && (
            <Link href="/interview" className={buttonClass("primary")}>
              Start an interview
            </Link>
          )
        }
      >
        {forRecruiter
          ? "This candidate has no graded answers and no parsed résumé."
          : "Finish an interview and each skill it covered will appear here with the evidence behind it."}
      </EmptyState>
    );
  }

  const sessionHref = (sessionId: string) =>
    forRecruiter ? `/recruiter/sessions/${sessionId}` : `/reports/${sessionId}`;

  return (
    <div className="flex flex-col gap-6">
      {map.skills.length === 0 && (
        <p className="text-ink-2">
          {forRecruiter
            ? "No answers have been graded yet, so every skill below is still a résumé claim."
            : "None of your answers have been graded yet, so every skill below is still a résumé claim."}
        </p>
      )}

      {ORDER.map((status) => {
        const skills = map.skills.filter((skill) => skill.status === status);
        if (skills.length === 0) return null;
        const meta = STATUS[status];
        return (
          <Card
            as="section"
            key={status}
            aria-labelledby={`skills-${status}`}
            className="flex flex-col gap-4 p-6 sm:p-7"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h2 id={`skills-${status}`} className="text-lg font-semibold">
                {meta.title}
                <span className="tabular ml-2 text-sm font-normal text-ink-3">{skills.length}</span>
              </h2>
              <span className="text-[13px] text-ink-3">{meta.blurb}</span>
            </div>
            <ul className="flex flex-col gap-2.5">
              {skills.map((skill, i) => (
                <li key={skill.name}>
                  <SkillRow skill={skill} delay={0.05 + i * 0.05} sessionHref={sessionHref} />
                </li>
              ))}
            </ul>
          </Card>
        );
      })}

      {map.not_assessed.length > 0 && (
        <Card as="section" aria-labelledby="skills-unassessed" className="flex flex-col gap-4 p-6 sm:p-7">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 id="skills-unassessed" className="text-lg font-semibold">
              Not assessed
              <span className="tabular ml-2 text-sm font-normal text-ink-3">
                {map.not_assessed.length}
              </span>
            </h2>
            <span className="text-[13px] text-ink-3">
              On the résumé, but no graded answer either way.
            </span>
          </div>
          <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
            {map.not_assessed.map((skill) => (
              <li
                key={skill.name}
                className="flex flex-col gap-1 rounded-control border border-dashed border-line-strong px-3.5 py-3"
              >
                <span className="font-semibold text-ink">{skill.name}</span>
                {skill.evidence_span && (
                  <span className="text-[13px] text-ink-3">
                    Résumé: &ldquo;{skill.evidence_span}&rdquo;
                  </span>
                )}
              </li>
            ))}
          </ul>
          {!forRecruiter && (
            <Link
              href="/interview"
              className={buttonClass("primary", "md", "group self-start")}
            >
              Start an interview
              <ArrowRight
                aria-hidden="true"
                className="size-4 transition-transform duration-200 group-hover:translate-x-0.5"
              />
            </Link>
          )}
        </Card>
      )}
    </div>
  );
}

function SkillRow({
  skill,
  delay,
  sessionHref,
}: {
  skill: SkillEvidence;
  delay: number;
  sessionHref: (sessionId: string) => string;
}) {
  const meta = STATUS[skill.status];
  const pct = toHundred(skill.score);
  const latest = skill.history[skill.history.length - 1];

  return (
    <details className="group rounded-control border border-line-soft bg-field open:bg-surface">
      <summary className="flex cursor-pointer list-none flex-col gap-2.5 px-4 py-3.5 marker:content-none">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          <span className="font-semibold text-ink">{skill.name}</span>
          <Chip tone={meta.tone}>{meta.label}</Chip>
          {skill.needs_review && (
            <span title="A recruiter is still checking an answer behind this score, so it may change.">
              <Chip tone="neutral">Under review</Chip>
            </span>
          )}
          <Trend score={skill.score} previous={skill.previous} />
          <span className="tabular ml-auto font-semibold text-ink">
            {pct}
            <span className="font-normal text-ink-3">/100</span>
          </span>
          <ChevronDown
            aria-hidden="true"
            className="size-4 text-ink-3 transition-transform duration-200 group-open:rotate-180"
          />
        </div>
        <div
          role="meter"
          aria-label={skill.name}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct}
          className="h-2 w-full overflow-hidden rounded-full bg-track"
        >
          <BarFill pct={pct} delay={delay} className={`h-full rounded-full ${meta.bar}`} />
        </div>
        <span className="text-[13px] text-ink-3">
          {skill.sessions === 1 ? "1 interview" : `${skill.sessions} interviews`} ·{" "}
          {skill.answers === 1 ? "1 answer" : `${skill.answers} answers`} · last asked{" "}
          {humanWhen(skill.last_assessed_at)}
          {skill.sessions > 1 && ` · best ${toHundred(skill.best)}`}
        </span>
      </summary>

      <div className="flex flex-col gap-4 border-t border-line-soft px-4 py-4">
        {skill.evidence.map((evidence) => (
          <Evidence key={evidence.question_id} evidence={evidence} />
        ))}
        <Link
          href={sessionHref(latest.session_id)}
          className="self-start text-[13px] font-semibold text-accent hover:text-brand"
        >
          Open the interview this comes from →
        </Link>
      </div>
    </details>
  );
}

/** How the latest score compares with the interview before it. */
function Trend({ score, previous }: { score: number; previous: number | null }) {
  if (previous === null) return null;
  const delta = toHundred(score) - toHundred(previous);
  if (delta === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-ink-3">
        <Minus aria-hidden="true" className="size-3.5" />
        no change
      </span>
    );
  }
  const up = delta > 0;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={`tabular inline-flex items-center gap-0.5 text-xs font-semibold ${up ? "text-ok" : "text-warn"}`}
    >
      <Icon aria-hidden="true" className="size-3.5" />
      {up ? "+" : "−"}
      {Math.abs(delta)} since the interview before
    </span>
  );
}

function Evidence({ evidence }: { evidence: QuestionEvidence }) {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-sm text-ink">{evidence.text}</p>
        <span className="tabular shrink-0 text-[13px] text-ink-2">
          {toHundred(evidence.score)}/100
        </span>
      </div>
      {evidence.concepts.length > 0 && (
        <ul className="flex flex-wrap gap-1.5" aria-label="Expected concepts">
          {evidence.concepts.map((concept) => (
            <li key={concept.concept}>
              <Concept concept={concept} />
            </li>
          ))}
        </ul>
      )}
      {evidence.sources.length > 0 && <ReadUp sources={evidence.sources} />}
    </div>
  );
}

function Concept({ concept }: { concept: ConceptEvidence }) {
  // The word is in the label, not only the colour, so it survives a screen
  // reader and a greyscale printout.
  if (concept.covered >= COVERED) {
    return (
      <Chip tone="ok">
        <Check aria-hidden="true" className="size-3.5" />
        <span className="sr-only">Covered: </span>
        {concept.concept}
      </Chip>
    );
  }
  if (concept.covered >= PARTLY) {
    return (
      <Chip tone="info">
        <Minus aria-hidden="true" className="size-3.5" />
        <span className="sr-only">Partly covered: </span>
        {concept.concept}
      </Chip>
    );
  }
  return (
    <Chip tone="warn">
      <X aria-hidden="true" className="size-3.5" />
      <span className="sr-only">Missed: </span>
      {concept.concept}
    </Chip>
  );
}

/**
 * The passages a question with a missed concept was built from. They are the
 * copies saved on the question when it was generated, so this is the material
 * the answer was actually graded against, not whatever the knowledge base says
 * today.
 */
function ReadUp({ sources }: { sources: CitedSource[] }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[11px] font-semibold tracking-[0.6px] text-ink-3 uppercase">
        Read up on what was missed
      </span>
      {sources.map((source) => (
        <details
          key={source.chunk_id}
          className="rounded-control border border-line-soft bg-field px-3.5 py-2.5"
        >
          <summary className="cursor-pointer list-none text-[13px] font-medium marker:content-none">
            <span className="text-accent">{source.heading_path}</span>
            {source.url && (
              <a
                href={source.url}
                target="_blank"
                rel="noreferrer"
                className="ml-2 text-xs font-normal text-ink-3 hover:text-accent"
                onClick={(event) => event.stopPropagation()}
              >
                source ↗
              </a>
            )}
          </summary>
          <p className="mt-2 text-[13px] leading-relaxed whitespace-pre-wrap text-ink-2">
            {source.text}
          </p>
          {source.license && (
            <p className="mt-2 text-[11px] text-ink-3">
              {source.document_title} — {source.license}
            </p>
          )}
        </details>
      ))}
    </div>
  );
}
