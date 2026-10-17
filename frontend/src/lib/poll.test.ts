/**
 * pollUntil's three exits — settled, failed, gave up — plus the two things
 * between them: riding out a blip, and stopping when the page goes away.
 * Fake timers make a three-minute wait take milliseconds.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { isAbort, pollUntil, PollTimeout, retryTransient } from "./poll";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("pollUntil", () => {
  it("checks before the first wait — an already-finished job costs no delay", async () => {
    const fetcher = vi.fn().mockResolvedValue("done");
    await expect(pollUntil(fetcher, (v) => v === "done")).resolves.toBe("done");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("settles when `done` says so", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce("pending")
      .mockResolvedValueOnce("pending")
      .mockResolvedValue("parsed");
    const result = pollUntil(fetcher, (v) => v === "parsed");
    await vi.advanceTimersByTimeAsync(5_000);
    await expect(result).resolves.toBe("parsed");
    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("stops at once on a 4xx — that's a real answer, not a blip", async () => {
    const fetcher = vi.fn().mockRejectedValue(new ApiError("Not found", 404));
    await expect(pollUntil(fetcher, () => true)).rejects.toMatchObject({ status: 404 });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("rides out network errors and 5xx, reporting them as it goes", async () => {
    const fetcher = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new ApiError("Bad gateway", 502))
      .mockResolvedValue("ok");
    const seen: string[] = [];
    const result = pollUntil(fetcher, () => true, {
      onConnectionChange: (problem) => seen.push(problem ? "problem" : "ok"),
    });
    await vi.advanceTimersByTimeAsync(5_000);
    await expect(result).resolves.toBe("ok");
    expect(seen).toEqual(["problem", "problem", "ok"]);
  });

  it("gives up with PollTimeout — distinct from a failure", async () => {
    const result = pollUntil(vi.fn().mockResolvedValue("pending"), () => false, {
      timeoutMs: 10_000,
    });
    const assertion = expect(result).rejects.toBeInstanceOf(PollTimeout);
    await vi.advanceTimersByTimeAsync(15_000);
    await assertion;
  });

  it("backs off: quick checks first, then at most every 5 s", async () => {
    const fetcher = vi.fn().mockResolvedValue("pending");
    pollUntil(fetcher, () => false, { timeoutMs: 60_000 }).catch(() => {});
    await vi.advanceTimersByTimeAsync(30_000);
    // 1 s, 1.5 s, 2.25 s, 3.4 s, then 5 s steps: far fewer than one per second.
    expect(fetcher.mock.calls.length).toBeGreaterThan(5);
    expect(fetcher.mock.calls.length).toBeLessThan(12);
  });

  it("stops promptly when aborted (the page unmounted)", async () => {
    const controller = new AbortController();
    const result = pollUntil(vi.fn().mockResolvedValue("pending"), () => false, {
      signal: controller.signal,
    });
    const assertion = expect(result).rejects.toSatisfy(isAbort);
    await vi.advanceTimersByTimeAsync(500);
    controller.abort();
    await assertion;
  });
});

describe("retryTransient", () => {
  it("sends once when the server answers", async () => {
    const op = vi.fn().mockResolvedValue("saved");
    await expect(retryTransient(op)).resolves.toBe("saved");
    expect(op).toHaveBeenCalledTimes(1);
  });

  it("rides out a restart — network errors and 5xx — and reports it", async () => {
    const op = vi
      .fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockRejectedValueOnce(new ApiError("Bad gateway", 502))
      .mockResolvedValueOnce("saved");
    const seen: unknown[] = [];
    const result = retryTransient(op, { onConnectionChange: (p) => seen.push(p) });
    await vi.advanceTimersByTimeAsync(10_000);
    await expect(result).resolves.toBe("saved");
    expect(op).toHaveBeenCalledTimes(3);
    // Shown while it was down, cleared once the answer landed.
    expect(seen.at(0)).toBeInstanceOf(TypeError);
    expect(seen.at(-1)).toBeNull();
  });

  it("throws a 4xx at once — the server answered, and said no", async () => {
    const op = vi.fn().mockRejectedValue(new ApiError("Session is EXPIRED", 409));
    await expect(retryTransient(op)).rejects.toMatchObject({ status: 409 });
    expect(op).toHaveBeenCalledTimes(1);
  });

  it("gives up with the last error once the time runs out", async () => {
    const op = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const seen: unknown[] = [];
    const result = retryTransient(op, {
      timeoutMs: 20_000,
      onConnectionChange: (p) => seen.push(p),
    });
    const assertion = expect(result).rejects.toBeInstanceOf(TypeError);
    await vi.advanceTimersByTimeAsync(30_000);
    await assertion;
    expect(seen.at(-1)).toBeNull(); // the "reconnecting" line doesn't linger
  });
});
