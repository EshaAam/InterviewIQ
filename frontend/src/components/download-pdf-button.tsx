"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { describeError, getReportPdf } from "@/lib/api";
import { saveFile } from "@/lib/download";
import { Button } from "./ui";

/** "Download PDF" for a session's report, with its own busy and error state. */
export function DownloadPdfButton({
  sessionId,
  asRecruiter = false,
  onDark = false,
}: {
  sessionId: string;
  /** The recruiter's copy adds the candidate's email and integrity signals. */
  asRecruiter?: boolean;
  /** Sits on a dark hero: the error text needs a light colour to be read. */
  onDark?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const pdf = await getReportPdf(sessionId, { asRecruiter });
      saveFile(pdf, `interviewiq-report-${sessionId.slice(0, 8)}.pdf`);
    } catch (err) {
      setError(describeError(err, "Could not download the PDF"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="flex items-center gap-2">
      {error && (
        <span role="alert" className={`text-xs ${onDark ? "text-[#ffb59a]" : "text-bad"}`}>
          {error}
        </span>
      )}
      <Button variant="secondary" onClick={download} loading={busy}>
        {!busy && <Download aria-hidden="true" className="size-4.5" />}
        {busy ? "Preparing…" : "Download PDF"}
      </Button>
    </span>
  );
}
