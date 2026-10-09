"use client";

/**
 * Record a spoken answer and turn it into editable text.
 *
 * The transcript is a draft: it is handed to `onTranscript`, which puts it in
 * the answer box for the candidate to correct (speech models mishear technical
 * words — "asyncio" can come back as "a SINGCO"). Submitting is the ordinary
 * typed-answer path, so a spoken answer is graded exactly like a typed one.
 *
 * Renders nothing where the browser cannot record (no MediaRecorder, or an
 * insecure origin), so the page never offers a button that cannot work.
 */

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Mic, Square } from "lucide-react";
import { describeError, transcribeAnswer } from "@/lib/api";
import { Button } from "@/components/ui";

type Phase = "idle" | "recording" | "transcribing";

export function canRecord(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.MediaRecorder !== "undefined" &&
    typeof navigator.mediaDevices?.getUserMedia === "function"
  );
}

// Browser capabilities never change while the page is open.
const subscribeNever = () => () => {};

export function VoiceRecorder({
  sessionId,
  questionId,
  maxSeconds,
  disabled = false,
  onTranscript,
}: {
  sessionId: string;
  questionId: string;
  maxSeconds: number;
  disabled?: boolean;
  onTranscript: (text: string) => void;
}) {
  // Client-only: the server render has no MediaRecorder to ask, so it says no
  // and the browser answers for real after hydration.
  const supported = useSyncExternalStore(subscribeNever, canRecord, () => false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  function releaseMic() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
  }

  // Leaving the question (the page keys this component by question) or the
  // page mid-recording must free the microphone and drop the clip.
  useEffect(() => {
    return () => {
      if (recorder.current && recorder.current.state !== "inactive") {
        recorder.current.onstop = null;
        recorder.current.stop();
      }
      releaseMic();
    };
  }, []);

  async function start() {
    setError(null);
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Microphone access was blocked. Allow it in the browser, or type your answer.");
      return;
    }
    chunks.current = [];
    const rec = new MediaRecorder(stream.current);
    rec.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.current.push(event.data);
    };
    rec.onstop = () => void finish(rec.mimeType);
    recorder.current = rec;
    rec.start();
    setSeconds(0);
    setPhase("recording");
    let elapsed = 0;
    timer.current = setInterval(() => {
      elapsed += 1;
      setSeconds(elapsed);
      // Stop at the server's limit rather than record audio it will refuse.
      if (elapsed >= maxSeconds) stop();
    }, 1000);
  }

  function stop() {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
    releaseMic();
  }

  async function finish(mimeType: string) {
    const audio = new Blob(chunks.current, { type: mimeType || "audio/webm" });
    chunks.current = [];
    if (audio.size === 0) {
      setPhase("idle");
      setError("Nothing was recorded. Try again, a little closer to the microphone.");
      return;
    }
    setPhase("transcribing");
    try {
      const transcript = await transcribeAnswer(sessionId, questionId, audio);
      if (transcript.text) {
        onTranscript(transcript.text);
      } else {
        setError("No speech was picked up in that recording.");
      }
    } catch (err) {
      setError(describeError(err, "Could not transcribe that recording. Try again."));
    } finally {
      setPhase("idle");
    }
  }

  if (!supported) return null;

  const left = Math.max(0, maxSeconds - seconds);
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-3">
        {phase === "recording" ? (
          <Button variant="danger" size="sm" onClick={stop}>
            <Square aria-hidden="true" className="size-3.5" />
            Stop recording
          </Button>
        ) : (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void start()}
            loading={phase === "transcribing"}
            disabled={disabled}
          >
            {phase !== "transcribing" && <Mic aria-hidden="true" className="size-3.5" />}
            {phase === "transcribing" ? "Transcribing…" : "Answer by voice"}
          </Button>
        )}
        <span className="text-[13px] text-ink-3" aria-live="polite">
          {phase === "recording"
            ? `Recording — ${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")} left`
            : "Your words appear in the box below to check and edit before you submit."}
        </span>
      </div>
      {error && (
        <p role="alert" className="text-[13px] text-bad">
          {error}
        </p>
      )}
    </div>
  );
}
