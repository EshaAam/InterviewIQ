/**
 * pollUntil's three exits — settled, failed, gave up — plus the two things
 * between them: riding out a blip, and stopping when the page goes away.
 * Fake timers make a three-minute wait take milliseconds.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import { isAbort, pollUntil, PollTimeout } from "./poll";

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
