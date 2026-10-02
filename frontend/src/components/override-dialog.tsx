"use client";

import { useEffect, useId, useState } from "react";
import { motion } from "motion/react";
import { SlidersHorizontal } from "lucide-react";
import { describeError } from "@/lib/api";
import { EASE } from "./motion";
import { Button, Card, ErrorBanner, FIELD_CLASS } from "./ui";

/**
 * "Set the final score" — used by the review queue and the session detail
 * page. Takes only the three numbers it shows, so either page can pass its
 * own row type. Render it inside `<AnimatePresence>` to get the exit motion.
 *
 * The slider's 0–1 range and 0.01 step mirror the backend's
 * `Field(ge=0.0, le=1.0)`, so the UI cannot build a request the schema
 * would reject.
 */
export function OverrideDialog({
  item,
  onCancel,
  onSave,
}: {
  item: { topic: string; final_score: number; deterministic_score: number };
  onCancel: () => void;
  onSave: (score: number, note: string | null) => Promise<void>;
}) {
  const [score, setScore] = useState(item.final_score);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const titleId = useId();

  // Escape closes, as every dialog does — unless a save is in flight.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await onSave(score, note.trim() || null);
    } catch (err) {
      setError(describeError(err, "Could not save the override"));
      setBusy(false);
    }
  }

  const pct = score * 100;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.2 }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-inverse/50 px-4 backdrop-blur-[2px]"
      onClick={() => !busy && onCancel()}
    >
      {/* role="dialog" + aria-modal tell assistive tech this is a dialog and the
          page behind it is inert; the title names it. */}
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        initial={{ opacity: 0, y: 18, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.98 }}
        transition={{ duration: 0.28, ease: EASE }}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[540px]"
      >
        <Card className="flex flex-col gap-5 p-7">
          <div className="flex items-start gap-3.5">
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-accent-subtle text-accent">
              <SlidersHorizontal aria-hidden="true" className="size-5" />
            </span>
            <div className="flex flex-col gap-1">
              <h2 id={titleId} className="font-display text-[22px] font-bold tracking-[-0.01em]">
                Set the final score
              </h2>
              <p className="text-sm text-ink-2">
                <span className="font-semibold text-ink">{item.topic}</span> · your score
                replaces the proposed {item.final_score.toFixed(2)}, clears this answer from
                the queue, and updates the candidate&apos;s report.
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-3 rounded-[14px] bg-canvas p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold">Final score</span>
              <motion.span
                key={score.toFixed(2)}
                initial={{ scale: 0.92 }}
                animate={{ scale: 1 }}
                className="tabular rounded-lg bg-surface px-3 py-1 font-display text-xl font-bold text-accent-strong shadow-card"
              >
                {score.toFixed(2)}
              </motion.span>
            </div>
            <input
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={score}
              onChange={(e) => setScore(Number(e.target.value))}
              aria-label="Final score"
              // Focus lands on the control the dialog exists for, so keyboard
              // users can adjust the score with the arrow keys straight away.
              autoFocus
              className="h-2 w-full cursor-pointer appearance-none rounded-full accent-accent"
              style={{
                background: `linear-gradient(90deg, var(--color-accent) ${pct}%, var(--color-track) ${pct}%)`,
              }}
            />
            <div className="tabular flex justify-between text-xs text-ink-3">
              <span>0.00</span>
              <span>rule {item.deterministic_score.toFixed(2)}</span>
              <span>proposed {item.final_score.toFixed(2)}</span>
              <span>1.00</span>
            </div>
          </div>

          <label className="flex flex-col gap-2">
            <span className="text-sm font-semibold">Why (recorded with your name)</span>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={4}
              className={`${FIELD_CLASS} resize-y text-sm leading-6`}
            />
          </label>

          <p className="text-xs text-ink-3">
            Both original passes stay on the evaluation record — an override adds your name
            and note, it does not erase what the graders said.
          </p>

          {error && <ErrorBanner message={error} />}

          <div className="flex items-center justify-end gap-3">
            <Button variant="secondary" onClick={onCancel} disabled={busy}>
              Cancel
            </Button>
            <Button onClick={save} loading={busy}>
              {busy ? "Saving…" : "Save override"}
            </Button>
          </div>
        </Card>
      </motion.div>
    </motion.div>
  );
}
