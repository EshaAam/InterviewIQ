import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SessionState } from "@/lib/api";
import { ScoreBar, StatusPill } from "./ui";

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

  it.each(STATES)("renders %s as the raw enum value", (state) => {
    render(<StatusPill state={state} />);
    // Same string as the API and the database, so a recruiter and a log agree.
    expect(screen.getByText(state).textContent).toBe(state);
  });
});
