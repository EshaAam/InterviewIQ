"use client"; // error boundaries must be client components

import { useEffect } from "react";
import Link from "next/link";
import { RotateCcw, TriangleAlert } from "lucide-react";
import { Button, buttonClass, Card, Shell } from "@/components/ui";

/**
 * Shown instead of a blank screen when a page throws while rendering.
 *
 * `retry` (stable since Next 16.3; it was `unstable_retry` in 16.2, and
 * tutorials still show the older `reset`) re-fetches and re-renders the
 * failed segment. The message stays generic: in production Next replaces
 * server error text with a digest, and a stack trace helps no candidate.
 */
export default function Error({
  error,
  retry,
}: {
  error: Error & { digest?: string };
  retry: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <Shell width="narrow">
      <Card className="flex flex-col items-start gap-4 p-8">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-bad-subtle text-bad">
          <TriangleAlert aria-hidden="true" className="size-6" />
        </span>
        <h1 className="font-display text-[28px] font-bold tracking-[-0.02em]">
          Something went wrong
        </h1>
        <p className="text-ink-2">
          This page hit an unexpected error. Your interview and answers are saved on the
          server — trying again usually works.
        </p>
        {error.digest && (
          <p className="tabular font-mono text-xs text-ink-3">Reference: {error.digest}</p>
        )}
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <Button onClick={() => retry()}>
            <RotateCcw aria-hidden="true" className="size-4" />
            Try again
          </Button>
          <Link href="/" className={buttonClass("secondary")}>
            Go to the home page
          </Link>
        </div>
      </Card>
    </Shell>
  );
}
