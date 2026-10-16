/**
 * Single entry point for talking to the backend.
 *
 * Components never call fetch directly — they go through here, so auth
 * headers, error shaping, and the base URL live in exactly one place.
 *
 * The types below are hand-mirrored from `app/schemas/interview.py` and
 * `app/schemas/auth.py`. When a schema changes on the backend, change it here
 * in the same commit — nothing else in the app knows the wire shape.
 */

import { formatBytes } from "./format";
import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  storeTokens,
  type TokenPair,
  type User,
} from "./auth";

// Trailing slashes stripped: every path below starts with one, and a pasted
// ".../api/v1/" would otherwise produce "//auth/register", which 404s.
const BASE_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(
  /\/+$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Every state the session FSM can be in — mirrors `SessionState`. */
export type SessionState =
  | "CREATED"
  | "PARSING"
  | "GENERATING_QS"
  | "READY"
  | "IN_PROGRESS"
  | "EVALUATING"
  | "COMPLETED"
  | "NEEDS_HUMAN_REVIEW"
  | "FAILED"
  | "EXPIRED";

export type ParseStatus = "pending" | "parsing" | "parsed" | "failed";

export type Skill = { name: string; confidence: number; evidence_span: string };
export type Resume = {
  id: string;
  parse_status: ParseStatus;
  /**
   * Why parsing failed, in words the candidate can act on. Present only when
   * `parse_status` is `failed`. The server distinguishes causes that clear in
   * minutes from ones that take hours, which is the difference between
   * "try again" and "come back later".
   */
  failure_reason: string | null;
  skills: Skill[];
};

export type Session = {
  id: string;
  state: SessionState;
  expires_at: string | null;
  failure_reason: string | null;
  answered: number;
  total_questions: number;
  /** Distinct question topics, in question order. Empty until questions exist. */
  topics: string[];
  created_at: string | null;
  /** Last state change; for a finished session, roughly when it finished. */
  updated_at: string | null;
};

export type Question = {
  id: string;
  ordinal: number;
  text: string;
  difficulty: string;
  topic: string;
};

export type Answer = { id: string; question_id: string; submitted_at: string };

/** One row of the candidate's own interview list. */
export type SessionSummary = Omit<Session, "created_at"> & {
  created_at: string;
  /** The report's overall score, once one exists. */
  overall: number | null;
};

/**
 * A knowledge-base passage a question was built from.
 *
 * `text` travels with it so a reviewer can check the grade against the same
 * material the grader saw, without a second request — the point of showing a
 * citation is that it can be checked, and a link nobody follows is not a check.
 */
export type CitedSource = {
  chunk_id: string;
  topic: string;
  heading_path: string;
  text: string;
  document_title: string;
  url: string;
  /** Non-empty only where the source licence requires visible attribution. */
  license: string;
};

/** A passage behind a concept the candidate missed. */
export type StudyLink = {
  topic: string;
  heading_path: string;
  document_title: string;
  url: string;
};

export type Report = {
  id: string;
  overall: number;
  per_topic: Record<string, number>;
  strengths: string[];
  gaps: string[];
  /** A recruiter overrode at least one score; the numbers include that. */
  human_reviewed: boolean;
  /** Passages behind the weakest topics. Empty when the interview was ungrounded. */
  study_links: StudyLink[];
};

export type RecruiterSession = {
  id: string;
  user_id: string;
  candidate_email: string;
  state: SessionState;
  created_at: string;
  /** Advisory: at least one answer tripped an integrity signal. */
  integrity_flag: boolean;
};

export type EvaluationReview = {
  id: string;
  answer_id: string;
  session_id: string;
  candidate_email: string;
  topic: string;
  question_text: string;
  answer_text: string;
  final_score: number;
  deterministic_score: number;
  confidence: number;
  needs_review: boolean;
  run_count: number;
  /** Whether the answer key came from cited passages or from model memory. */
  grounded: boolean;
  sources: CitedSource[];
};

/** A page of the review queue, plus how big the whole queue is. */
export type EvaluationReviewPage = { items: EvaluationReview[]; total: number };

export type EvaluationDetail = {
  id: string;
  deterministic_score: number;
  final_score: number;
  confidence: number;
  needs_review: boolean;
  run_count: number;
  /** The model's rubric: correctness / depth / clarity, 0..1 each. */
  llm_scores: Record<string, number>;
  overridden_by_id: string | null;
  override_note: string | null;
};

/** A hint for a human, never a verdict — and never applied to a score. */
export type IntegritySignal = {
  /**
   * `prompt_injection` comes from the text itself (an attempt to instruct the
   * AI); the other two from browser-reported typing telemetry.
   */
  code: "mostly_pasted" | "too_fast" | "prompt_injection";
  /** A sentence ready to show as-is. */
  detail: string;
};

export type AnswerDetail = {
  id: string;
  text: string;
  submitted_at: string;
  time_taken_ms: number | null;
  paste_events: number;
  keystroke_count: number | null;
  evaluation: EvaluationDetail | null;
  /** Characters the server matched to this question's voice transcripts. */
  dictated_chars: number;
  integrity: IntegritySignal[];
};

export type QuestionDetail = {
  id: string;
  ordinal: number;
  topic: string;
  difficulty: string;
  text: string;
  expected_concepts: string[];
  grounded: boolean;
  sources: CitedSource[];
  answers: AnswerDetail[];
};

export type RecruiterSessionDetail = {
  id: string;
  user_id: string;
  candidate_email: string;
  state: SessionState;
  created_at: string;
  expires_at: string | null;
  failure_reason: string | null;
  job_description: string | null;
  /** Requirements the résumé did not evidence, as computed at generation time. */
  jd_gaps: string[];
  /** Signals on the résumé the questions came from — today only prompt injection. */
  resume_integrity: IntegritySignal[];
  questions: QuestionDetail[];
  report: Report | null;
  integrity_flag: boolean;
};

export type OverrideResult = {
  id: string;
  final_score: number;
  needs_review: boolean;
  overridden_by_id: string | null;
  /** The session's state after the report was rebuilt. */
  session_state: SessionState | null;
};

type FetchOptions = RequestInit & { skipAuth?: boolean };

async function rawFetch(path: string, init: FetchOptions): Promise<Response> {
  const { skipAuth, ...rest } = init;
  // `new Headers(...)` accepts every shape a caller might pass (plain object,
  // array of pairs, or a Headers instance) — spreading only handled the first.
  const headers = new Headers(rest.headers);
  // Only JSON string bodies get a JSON content type. A GET with no body then
  // skips the CORS preflight, and a future FormData upload keeps the
  // multipart boundary the browser writes for it.
  if (typeof rest.body === "string" && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const token = skipAuth ? null : getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${BASE_URL}${path}`, { ...rest, headers });
}

/**
 * The refresh in flight, shared by every request that hits a 401 at the same
 * moment. Without it, a page that fires two requests together (the report
 * page does) would spend the refresh token twice — harmless today, a forced
 * sign-out the day the backend starts rotating refresh tokens.
 */
let refreshing: Promise<void> | null = null;

function refreshTokens(): Promise<void> {
  refreshing ??= (async () => {
    const refresh_token = getRefreshToken();
    if (!refresh_token) throw new ApiError("Not signed in", 401);

    const refreshed = await rawFetch("/auth/refresh", {
      method: "POST",
      body: JSON.stringify({ refresh_token }),
      skipAuth: true,
    });
    if (!refreshed.ok) {
      // The session is genuinely over. Clearing fires TOKENS_CHANGED, which
      // the authenticated layout hears and answers with a trip to /login.
      clearTokens();
      throw new ApiError("Session expired — sign in again", 401);
    }
    storeTokens((await refreshed.json()) as TokenPair);
  })().finally(() => {
    refreshing = null;
  });
  return refreshing;
}

/**
 * A 401 on an access token is usually just expiry, so refresh once and replay
 * the original request. The replay goes through rawFetch, not apiFetch:
 * exactly one retry, never a loop.
 */
async function refreshAndRetry(path: string, init: FetchOptions): Promise<Response> {
  await refreshTokens();
  return rawFetch(path, init);
}

/**
 * One request with the app's rules applied: auth header, one silent refresh
 * on a 401, and an ApiError for any non-2xx. Returns the raw Response so a
 * caller can read it as JSON (apiFetch) or as a file (getReportPdf).
 */
async function request(path: string, init: FetchOptions = {}): Promise<Response> {
  let response = await rawFetch(path, init);

  if (response.status === 401 && !init.skipAuth) {
    response = await refreshAndRetry(path, init);
  }

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status);
  }
  return response;
}

export async function apiFetch<T>(path: string, init: FetchOptions = {}): Promise<T> {
  const response = await request(path, init);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/**
 * The sentence to show a person for a failed call. Statuses that mean the same
 * thing everywhere get one wording app-wide; the rest use the backend's own
 * `detail`, and anything that isn't an ApiError (a network failure) gets the
 * caller's fallback.
 */
export function describeError(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  if (err.status === 429) {
    return "You are over your daily token budget — try again after midnight UTC.";
  }
  return err.message;
}

/** FastAPI puts the human-readable reason in `detail`; fall back to the status. */
async function errorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") return body.detail;
    if (Array.isArray(body?.detail)) return body.detail[0]?.msg ?? "Invalid request";
  } catch {
    /* not JSON — fall through */
  }
  return `Request failed (${response.status})`;
}

/**
 * Fire-and-forget liveness ping. The free Render instance sleeps after 15
 * idle minutes and takes about a minute to wake; the public landing page calls
 * this on arrival so that by the time someone has read it and signed in, the
 * API is already up. Failure is irrelevant, so nothing is surfaced.
 */
export function wakeBackend(): void {
  fetch(`${BASE_URL}/health`, { cache: "no-store" }).catch(() => {});
}

// --- Auth ---

export async function login(email: string, password: string): Promise<TokenPair> {
  const pair = await apiFetch<TokenPair>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipAuth: true,
  });
  storeTokens(pair);
  return pair;
}

/**
 * Self-service sign-up always creates a candidate. Recruiter accounts are
 * made on the server (`python -m app.cli create-recruiter`), never chosen here.
 */
export async function register(email: string, password: string): Promise<User> {
  return apiFetch<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
    skipAuth: true,
  });
}

export function me(): Promise<User> {
  return apiFetch<User>("/auth/me");
}

// --- Resumes ---

/** 202 — the row exists immediately, parsing runs in a worker. Poll getResume. */
export function createResume(text: string, mime = "text/plain"): Promise<Resume> {
  return apiFetch<Resume>("/resumes", {
    method: "POST",
    body: JSON.stringify({ text, mime }),
  });
}

/** Mirrors the backend's RESUME_MAX_BYTES, so an oversize file is caught before upload. */
export const RESUME_MAX_BYTES = 2 * 1024 * 1024;
export const RESUME_EXTENSIONS = [".pdf", ".docx", ".txt"] as const;

/**
 * What's wrong with a chosen file, in a sentence, or null if it looks fine.
 * Only the extension and size: the server checks again, properly, from the
 * bytes — this exists to fail fast with a clear message, not for trust.
 */
export function resumeProblem(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!RESUME_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Choose a PDF, DOCX or TXT file.";
  }
  if (file.size > RESUME_MAX_BYTES) {
    return `That file is ${formatBytes(file.size)} — the limit is 2 MB.`;
  }
  return null;
}

/**
 * 202 — by the time this returns, the backend has already checked the file and
 * pulled its text out (a scan with no text is a 422 here, not a failure later).
 * Skill extraction still runs in a worker: poll getResume, as for pasted text.
 */
export function uploadResume(file: File): Promise<Resume> {
  const body = new FormData();
  body.append("file", file);
  // No Content-Type here: the browser writes the multipart boundary itself,
  // and rawFetch only adds JSON's content type to string bodies.
  return apiFetch<Resume>("/resumes/upload", { method: "POST", body });
}

export function getResume(resumeId: string): Promise<Resume> {
  return apiFetch<Resume>(`/resumes/${resumeId}`);
}

// --- Sessions ---

/**
 * 202 — question generation is dispatched; poll until the state is READY.
 *
 * An optional job description shifts what the interview is for: generation
 * targets the requirements the résumé does not evidence, rather than the skills
 * it already does.
 */
export function createSession(
  resumeId: string,
  jobDescription?: string,
): Promise<Session> {
  return apiFetch<Session>("/sessions", {
    method: "POST",
    body: JSON.stringify({
      resume_id: resumeId,
      job_description: jobDescription?.trim() || null,
    }),
  });
}

/** The signed-in user's own interviews, newest first. */
export function listMySessions(): Promise<SessionSummary[]> {
  return apiFetch<SessionSummary[]>("/sessions");
}

export function getSession(sessionId: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${sessionId}`);
}

/** Starts the server-side clock. Only legal from READY. */
export function startSession(sessionId: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${sessionId}/start`, { method: "POST" });
}

export function nextQuestion(sessionId: string): Promise<Question> {
  return apiFetch<Question>(`/sessions/${sessionId}/questions/next`);
}

/**
 * The Idempotency-Key header is required, not optional: a retried submit must
 * return the original answer rather than creating a second one.
 */
export function submitAnswer(
  sessionId: string,
  body: {
    question_id: string;
    text: string;
    time_taken_ms?: number;
    paste_events: number;
    keystroke_count?: number;
  },
  idempotencyKey: string,
): Promise<Answer> {
  return apiFetch<Answer>(`/sessions/${sessionId}/answers`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

// --- Voice answers ---

/** Optional capabilities the server offers; the UI hides what it lacks. */
export type Features = { voice_answers: boolean; voice_max_seconds: number };

/** A draft for the candidate to check and edit — not yet an answer. */
export type Transcript = { text: string; duration_seconds: number; language: string };

export function getFeatures(): Promise<Features> {
  return apiFetch<Features>("/features", { skipAuth: true });
}

/**
 * Speech-to-text for one recording. The result goes into the answer box for
 * the candidate to correct; it is submitted through `submitAnswer` like any
 * typed answer, so it is graded by the same pipeline.
 */
export function transcribeAnswer(
  sessionId: string,
  questionId: string,
  audio: Blob,
): Promise<Transcript> {
  const body = new FormData();
  body.append("question_id", questionId);
  body.append("audio", audio, audioFilename(audio.type));
  return apiFetch<Transcript>(`/sessions/${sessionId}/transcribe`, { method: "POST", body });
}

function audioFilename(mime: string): string {
  if (mime.includes("ogg")) return "answer.ogg";
  if (mime.includes("mp4") || mime.includes("aac")) return "answer.m4a";
  if (mime.includes("wav")) return "answer.wav";
  return "answer.webm";
}

export function finishSession(sessionId: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${sessionId}/finish`, { method: "POST" });
}

export function getReport(sessionId: string): Promise<Report> {
  return apiFetch<Report>(`/sessions/${sessionId}/report`);
}

/**
 * The report as a PDF. A plain `<a href>` can't fetch it — links don't send
 * the Authorization header — so it comes through the same authenticated
 * request as everything else and is handed back as a Blob to save.
 * The recruiter's copy adds the candidate's email and integrity signals.
 */
export async function getReportPdf(
  sessionId: string,
  { asRecruiter = false }: { asRecruiter?: boolean } = {},
): Promise<Blob> {
  const path = asRecruiter
    ? `/recruiter/sessions/${sessionId}/report.pdf`
    : `/sessions/${sessionId}/report.pdf`;
  return (await request(path)).blob();
}

// --- Recruiter ---

export function listSessions(params: {
  state?: SessionState;
  limit?: number;
  offset?: number;
}): Promise<RecruiterSession[]> {
  const query = new URLSearchParams();
  if (params.state) query.set("state", params.state);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  return apiFetch<RecruiterSession[]>(`/recruiter/sessions?${query}`);
}

export function getRecruiterSession(sessionId: string): Promise<RecruiterSessionDetail> {
  return apiFetch<RecruiterSessionDetail>(`/recruiter/sessions/${sessionId}`);
}

export function reviewQueue(
  params: { limit?: number; offset?: number } = {},
): Promise<EvaluationReviewPage> {
  const query = new URLSearchParams({ needs_review: "true" });
  if (params.limit) query.set("limit", String(params.limit));
  if (params.offset) query.set("offset", String(params.offset));
  return apiFetch<EvaluationReviewPage>(`/recruiter/evaluations?${query}`);
}

export function overrideEvaluation(
  evaluationId: string,
  final_score: number,
  note: string | null,
): Promise<OverrideResult> {
  return apiFetch<OverrideResult>(`/recruiter/evaluations/${evaluationId}/override`, {
    method: "POST",
    body: JSON.stringify({ final_score, note }),
  });
}

export type LLMCall = {
  id: string;
  session_id: string | null;
  provider: string;
  model: string;
  prompt_tokens: number;
  completion_tokens: number;
  cost_estimate: number;
  latency_ms: number;
  status: string;
  created_at: string;
};

export type CostSummary = {
  tokens_today: number;
  spend_today: number;
  calls_today: number;
  failed_today: number;
  daily_token_budget: number;
  recent: LLMCall[];
};

export function getCosts(limit = 25): Promise<CostSummary> {
  return apiFetch<CostSummary>(`/recruiter/costs?limit=${limit}`);
}

export type HealthResponse = { status: string; environment: string };
