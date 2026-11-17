import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { SkillEvidence, SkillMap } from "@/lib/api";
import { countByStatus, SkillMapView } from "./skill-map";

afterEach(cleanup);

const WHEN = "2026-11-10T09:00:00Z";

function skill(overrides: Partial<SkillEvidence> & Pick<SkillEvidence, "name">): SkillEvidence {
  return {
    status: "weak",
    score: 0.3,
    best: 0.3,
    previous: null,
    sessions: 1,
    answers: 1,
    last_assessed_at: WHEN,
    needs_review: false,
    history: [{ session_id: "s-latest", assessed_at: WHEN, score: 0.3 }],
    evidence: [],
    ...overrides,
  };
}

const MAP: SkillMap = {
  candidate_email: null,
  sessions_assessed: 2,
  skills: [
    skill({
      name: "sql",
      score: 0.3,
      previous: 0.6,
      sessions: 2,
      answers: 2,
      evidence: [
        {
          question_id: "q1",
          session_id: "s-latest",
          text: "How does a B-tree index speed up a range scan?",
          score: 0.3,
          concepts: [
            { concept: "sorted keys", covered: 1 },
            { concept: "leaf links", covered: 0.5 },
            { concept: "write cost", covered: 0 },
          ],
          sources: [
            {
              chunk_id: "c1",
              topic: "sql",
              heading_path: "SQL > Indexes",
              text: "A B-tree index keeps keys sorted.",
              document_title: "SQL",
              url: "",
              license: "",
            },
          ],
        },
      ],
    }),
    skill({ name: "python", status: "demonstrated", score: 0.9, best: 0.9, needs_review: true }),
  ],
  not_assessed: [{ name: "kubernetes", confidence: 0.6, evidence_span: "ran k8s clusters" }],
};

describe("countByStatus", () => {
  it("counts every status, including the ones with no skills", () => {
    expect(countByStatus(MAP)).toEqual({ weak: 1, developing: 0, demonstrated: 1 });
  });
});

describe("SkillMapView", () => {
  it("groups skills by where they stand and skips empty groups", () => {
    render(<SkillMapView map={MAP} />);
    expect(screen.getByRole("heading", { name: /Needs work/ })).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Demonstrated/ })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /Developing/ })).toBeNull();
    expect(screen.getByRole("meter", { name: "sql" }).getAttribute("aria-valuenow")).toBe("30");
  });

  it("says in words whether each concept was covered, partly covered or missed", () => {
    render(<SkillMapView map={MAP} />);
    const concepts = within(screen.getByRole("list", { name: "Expected concepts" }));
    expect(concepts.getByText(/^Covered:/)).toBeTruthy();
    expect(concepts.getByText(/^Partly covered:/)).toBeTruthy();
    expect(concepts.getByText(/^Missed:/)).toBeTruthy();
  });

  it("puts the cited passage next to a question with a missed concept", () => {
    render(<SkillMapView map={MAP} />);
    expect(screen.getByText("SQL > Indexes")).toBeTruthy();
    expect(screen.getByText("A B-tree index keeps keys sorted.")).toBeTruthy();
  });

  it("shows the change since the interview before", () => {
    render(<SkillMapView map={MAP} />);
    expect(screen.getByText(/30 since the interview before/)).toBeTruthy();
  });

  it("marks a skill whose latest score is still under review", () => {
    render(<SkillMapView map={MAP} />);
    expect(screen.getAllByText("Under review")).toHaveLength(1);
  });

  it("lists résumé skills no interview has graded", () => {
    render(<SkillMapView map={MAP} />);
    expect(screen.getByRole("heading", { name: /Not assessed/ })).toBeTruthy();
    expect(screen.getByText("kubernetes")).toBeTruthy();
    expect(screen.getByText(/ran k8s clusters/)).toBeTruthy();
  });

  it("sends a candidate to their report and a recruiter to the session review", () => {
    const { unmount } = render(<SkillMapView map={MAP} />);
    const candidate = screen.getAllByRole("link", { name: /Open the interview/ })[0];
    expect(candidate.getAttribute("href")).toBe("/reports/s-latest");
    expect(screen.getByRole("link", { name: /Start an interview/ })).toBeTruthy();
    unmount();

    render(<SkillMapView map={MAP} forRecruiter />);
    const recruiter = screen.getAllByRole("link", { name: /Open the interview/ })[0];
    expect(recruiter.getAttribute("href")).toBe("/recruiter/sessions/s-latest");
    // A recruiter cannot start an interview on a candidate's behalf.
    expect(screen.queryByRole("link", { name: /Start an interview/ })).toBeNull();
  });

  it("explains an empty map instead of rendering nothing", () => {
    render(
      <SkillMapView
        map={{ candidate_email: null, sessions_assessed: 0, skills: [], not_assessed: [] }}
      />,
    );
    expect(screen.getByText("Nothing to map yet")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Start an interview/ })).toBeTruthy();
  });
});
