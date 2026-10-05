import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SessionState } from "@/lib/api";
import { ScoreBar, STATE_LABEL, StatusPill } from "./ui";

afterEach(cleanup);

describe("ScoreBar", () => {
  it.each([
    [0.72, 72],
    [1.7, 100], // a bad score must fill its track, not overflow the card
    [-0.3, 0],
  ])("score %s fills %s%%", (score, pct) => {
    render(<ScoreBar topic="python" score={score} />);
    const meter = screen.getByRole("meter", { name: "python" });
    expect(meter.getAttribute("aria-valuenow")).toBe(String(pct));
    expect((meter.firstElementChild as HTMLElement).style.width).toBe(`${pct}%`);
  });
});

describe("StatusPill", () => {
  const STATES: SessionState[] = [
    "CREATED",
    "PARSING",
    "GENERATING_QS",
    "READY",
    "IN_PROGRESS",
    "EVALUATING",
    "COMPLETED",
    "NEEDS_HUMAN_REVIEW",
    "FAILED",
    "EXPIRED",
  ];

  it.each(STATES)("shows %s in plain English", (state) => {
    render(<StatusPill state={state} />);
    const pill = screen.getByText(STATE_LABEL[state]);
    // A candidate should never read an enum like NEEDS_HUMAN_REVIEW.
    expect(pill.textContent).not.toContain("_");
    expect(pill.textContent).not.toBe(state);
  });

  it.each(STATES)("keeps the raw %s value in the hover title", (state) => {
    render(<StatusPill state={state} />);
    // So a recruiter matching the pill against an API response or a database
    // row still has the exact string.
    expect(screen.getByText(STATE_LABEL[state]).getAttribute("title")).toBe(state);
  });

  it("gives every state a distinct label", () => {
    // Two states sharing a label would make the filter chips ambiguous.
    const labels = STATES.map((s) => STATE_LABEL[s]);
    expect(new Set(labels).size).toBe(labels.length);
  });
});
