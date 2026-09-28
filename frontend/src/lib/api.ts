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

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  storeTokens,
  type TokenPair,
  type User,
  type UserRole,
} from "./auth";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

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
export type Resume = { id: string; parse_status: ParseStatus; skills: Skill[] };

export type Session = {
  id: string;
  state: SessionState;
  expires_at: string | null;
  failure_reason: string | null;
  answered: number;
  total_questions: number;
};

export type Question = {
  id: string;
  ordinal: number;
  text: string;
  difficulty: string;
  topic: string;
};

export type Answer = { id: string; question_id: string; submitted_at: string };

export type Report = {
  id: string;
  overall: number;
  per_topic: Record<string, number>;
  strengths: string[];
  gaps: string[];
};

export type RecruiterSession = {
  id: string;
  user_id: string;
  state: SessionState;
  created_at: string;
};

export type EvaluationReview = {
  id: string;
  answer_id: string;
  topic: string;
  question_text: string;
  answer_text: string;
  final_score: number;
  deterministic_score: number;
  confidence: number;
  needs_review: boolean;
  run_count: number;
};

export type OverrideResult = {
  id: string;
  final_score: number;
  needs_review: boolean;
  overridden_by_id: string | null;
};

type FetchOptions = RequestInit & { skipAuth?: boolean };

async function rawFetch(path: string, init: FetchOptions): Promise<Response> {
  const { skipAuth, ...rest } = init;
  const token = skipAuth ? null : getAccessToken();
  return fetch(`${BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...rest.headers,
    },
  });
}

/**
 * A 401 on an access token is usually just expiry, so spend the refresh token
 * once and replay the original request. If the refresh also fails the session
 * is genuinely over — drop both tokens so the UI can send them to /login.
 */
async function refreshAndRetry(path: string, init: FetchOptions): Promise<Response> {
  const refresh_token = getRefreshToken();
  if (!refresh_token) throw new ApiError("Not signed in", 401);

  const refreshed = await rawFetch("/auth/refresh", {
    method: "POST",
    body: JSON.stringify({ refresh_token }),
    skipAuth: true,
  });
  if (!refreshed.ok) {
    clearTokens();
    throw new ApiError("Session expired — sign in again", 401);
  }
  storeTokens((await refreshed.json()) as TokenPair);
  return rawFetch(path, init);
}

export async function apiFetch<T>(path: string, init: FetchOptions = {}): Promise<T> {
  let response = await rawFetch(path, init);

  if (response.status === 401 && !init.skipAuth) {
    response = await refreshAndRetry(path, init);
  }

  if (!response.ok) {
    throw new ApiError(await errorDetail(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
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

export async function register(
  email: string,
  password: string,
  role: UserRole,
): Promise<User> {
  return apiFetch<User>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, role }),
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

export function getResume(resumeId: string): Promise<Resume> {
  return apiFetch<Resume>(`/resumes/${resumeId}`);
}

// --- Sessions ---

/** 202 — question generation is dispatched; poll until the state is READY. */
export function createSession(resumeId: string): Promise<Session> {
  return apiFetch<Session>("/sessions", {
    method: "POST",
    body: JSON.stringify({ resume_id: resumeId }),
  });
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

export function finishSession(sessionId: string): Promise<Session> {
  return apiFetch<Session>(`/sessions/${sessionId}/finish`, { method: "POST" });
}

export function getReport(sessionId: string): Promise<Report> {
  return apiFetch<Report>(`/sessions/${sessionId}/report`);
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

export function reviewQueue(needsReview = true): Promise<EvaluationReview[]> {
  return apiFetch<EvaluationReview[]>(
    `/recruiter/evaluations?needs_review=${needsReview}`,
  );
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
