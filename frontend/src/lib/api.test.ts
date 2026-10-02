/**
 * The API client's invisible-when-it-works paths: the silent token refresh,
 * error shaping, and request headers. When these break, the symptom is
 * "everyone gets signed out" or "uploads fail", far from the cause.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, describeError, getReportPdf, uploadResume } from "./api";
import { getAccessToken, storeTokens, TOKENS_CHANGED } from "./auth";

type Call = { url: string; init: RequestInit };

let calls: Call[];

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Stub fetch with a handler; record every call. */
function serve(handler: (url: string, init: RequestInit) => Response | Promise<Response>) {
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return handler(url, init);
  });
}

/** The ApiError a call rejects with — and a failed test if it resolves. */
async function failure(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(ApiError);
    return error as ApiError;
  }
  throw new Error("expected the call to fail, but it succeeded");
}

function headerOf(call: Call, name: string): string | null {
  return new Headers(call.init.headers).get(name);
}

beforeEach(() => {
  calls = [];
  localStorage.clear();
  storeTokens({ access_token: "old", refresh_token: "r1", token_type: "bearer" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("silent refresh", () => {
  it("refreshes once on a 401 and replays the request", async () => {
    serve((url, init) => {
      if (url.endsWith("/auth/refresh")) {
        return json({ access_token: "new", refresh_token: "r2", token_type: "bearer" });
      }
      return new Headers(init.headers).get("Authorization") === "Bearer old"
        ? json({ detail: "expired" }, 401)
        : json({ ok: true });
    });

    await expect(apiFetch("/thing")).resolves.toEqual({ ok: true });
    expect(calls.map((c) => c.url.split("/api/v1")[1])).toEqual([
      "/thing",
      "/auth/refresh",
      "/thing",
    ]);
    // The refresh itself never carries the dead access token.
    expect(headerOf(calls[1], "Authorization")).toBeNull();
    expect(getAccessToken()).toBe("new");
  });

  it("shares one refresh between concurrent 401s", async () => {
    let refreshes = 0;
    serve(async (url, init) => {
      if (url.endsWith("/auth/refresh")) {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 10));
        return json({ access_token: "new", refresh_token: "r2", token_type: "bearer" });
      }
      return new Headers(init.headers).get("Authorization") === "Bearer old"
        ? json({}, 401)
        : json({ path: url });
    });

    await Promise.all([apiFetch("/a"), apiFetch("/b"), apiFetch("/c")]);
    expect(refreshes).toBe(1);
  });

  it("signs out when the refresh fails: clears tokens and announces it", async () => {
    serve(() => json({ detail: "nope" }, 401));
    const heard = vi.fn();
    window.addEventListener(TOKENS_CHANGED, heard);

    const error = await failure(apiFetch("/thing"));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(401);
    expect(getAccessToken()).toBeNull();
    expect(heard).toHaveBeenCalled();
    window.removeEventListener(TOKENS_CHANGED, heard);
  });
});

describe("error shaping", () => {
  it.each([
    ["HTTPException detail", json({ detail: "Session is EXPIRED" }, 409), "Session is EXPIRED"],
    [
      "Pydantic 422 list",
      json({ detail: [{ msg: "field required", loc: ["body", "text"] }] }, 422),
      "field required",
    ],
    ["non-JSON (a proxy's HTML page)", new Response("<html>502</html>", { status: 502 }), "Request failed (502)"],
  ])("%s", async (_, response, message) => {
    serve(() => response);
    const error = await failure(apiFetch("/x"));
    expect(error).toBeInstanceOf(ApiError);
    expect(error.message).toBe(message);
  });

  it("describeError: one wording for 429, the detail otherwise, a fallback for network errors", () => {
    expect(describeError(new ApiError("Daily token budget exceeded", 429), "f")).toMatch(/budget/);
    expect(describeError(new ApiError("Resume not found", 404), "f")).toBe("Resume not found");
    expect(describeError(new TypeError("Failed to fetch"), "Could not reach the server")).toBe(
      "Could not reach the server",
    );
  });
});

describe("request headers", () => {
  it("sends a JSON content type only with a JSON body", async () => {
    serve(() => json({}));
    await apiFetch("/get");
    await apiFetch("/post", { method: "POST", body: JSON.stringify({ a: 1 }) });
    // No Content-Type on a bodiless GET means no CORS preflight for it.
    expect(headerOf(calls[0], "Content-Type")).toBeNull();
    expect(headerOf(calls[1], "Content-Type")).toBe("application/json");
  });

  it("uploads as multipart: FormData body, no JSON content type", async () => {
    serve(() => json({ id: "r1", parse_status: "pending", skills: [] }, 202));
    await uploadResume(new File(["%PDF-1.4"], "cv.pdf", { type: "application/pdf" }));
    expect(calls[0].init.body).toBeInstanceOf(FormData);
    // The browser must write multipart/form-data with its own boundary.
    expect(headerOf(calls[0], "Content-Type")).toBeNull();
  });

  it("downloads the PDF as a Blob, from the recruiter route when asked", async () => {
    serve(() => new Response(new Uint8Array([37, 80, 68, 70]), { status: 200 }));
    const blob = await getReportPdf("abc", { asRecruiter: true });
    expect(blob.size).toBe(4);
    expect(calls[0].url).toMatch(/\/recruiter\/sessions\/abc\/report\.pdf$/);
  });
});
