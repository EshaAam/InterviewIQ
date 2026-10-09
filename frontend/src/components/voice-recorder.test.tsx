/**
 * The recorder: hidden where a browser cannot record, and otherwise a round
 * trip from microphone to editable text. MediaRecorder and getUserMedia are
 * stubbed — jsdom has neither — so these test our wiring, not the browser's.
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { storeTokens } from "@/lib/auth";
import { VoiceRecorder } from "./voice-recorder";

class FakeMediaRecorder {
  state: "inactive" | "recording" = "inactive";
  mimeType = "audio/webm;codecs=opus";
  ondataavailable: ((event: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["opus bytes"], { type: this.mimeType }) });
    this.onstop?.();
  }
}

const stopTrack = vi.fn();
let requests: { url: string; body: FormData }[];

function renderRecorder(onTranscript = vi.fn()) {
  render(
    <VoiceRecorder sessionId="s1" questionId="q1" maxSeconds={180} onTranscript={onTranscript} />,
  );
  return onTranscript;
}

beforeEach(() => {
  requests = [];
  storeTokens({ access_token: "a", refresh_token: "r", token_type: "bearer" });
  vi.stubGlobal("MediaRecorder", FakeMediaRecorder);
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: {
      getUserMedia: vi.fn(async () => ({ getTracks: () => [{ stop: stopTrack }] })),
    },
  });
  vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
    requests.push({ url, body: init.body as FormData });
    return new Response(
      JSON.stringify({ text: "the GIL serialises bytecode", duration_seconds: 4, language: "en" }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    );
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  stopTrack.mockClear();
});

describe("VoiceRecorder", () => {
  it("renders nothing where the browser cannot record", () => {
    vi.stubGlobal("MediaRecorder", undefined);
    renderRecorder();
    expect(screen.queryByRole("button", { name: /voice/i })).toBeNull();
  });

  it("records, uploads the clip for its question, and hands back the draft", async () => {
    const onTranscript = renderRecorder();

    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Answer by voice" })));
    expect(screen.getByText(/Recording — 3:00 left/)).toBeTruthy();

    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Stop recording" })));

    await waitFor(() => expect(onTranscript).toHaveBeenCalledWith("the GIL serialises bytecode"));
    expect(requests).toHaveLength(1);
    expect(requests[0].url).toMatch(/\/sessions\/s1\/transcribe$/);
    expect(requests[0].body.get("question_id")).toBe("q1");
    expect((requests[0].body.get("audio") as File).name).toBe("answer.webm");
    // The microphone is released as soon as recording stops.
    expect(stopTrack).toHaveBeenCalled();
  });

  it("explains a blocked microphone instead of failing silently", async () => {
    (navigator.mediaDevices.getUserMedia as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new Error("NotAllowedError"),
    );
    const onTranscript = renderRecorder();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Answer by voice" })));
    expect(screen.getByRole("alert").textContent).toMatch(/Microphone access was blocked/);
    expect(onTranscript).not.toHaveBeenCalled();
  });

  it("shows the server's reason when a recording is refused", async () => {
    vi.stubGlobal(
      "fetch",
      async () =>
        new Response(JSON.stringify({ detail: "Recordings can be up to 180 seconds." }), {
          status: 413,
          headers: { "Content-Type": "application/json" },
        }),
    );
    renderRecorder();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Answer by voice" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Stop recording" })));
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toBe("Recordings can be up to 180 seconds."),
    );
  });
});
