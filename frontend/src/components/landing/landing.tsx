"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { wakeBackend } from "@/lib/api";
import { setPendingResume } from "@/lib/pending-resume";
import { destinationFor, loginHref, useUser } from "@/lib/use-user";
import { Hero } from "./hero";
import { SiteFooter } from "@/components/site-footer";
import { SiteNav } from "@/components/site-nav";
import {
  Features,
  FinalCta,
  Grading,
  HowItWorks,
  Recruiters,
  TopicMarquee,
} from "./sections";

/**
 * The public landing page. Open to everyone; the only thing gated is the
 * upload itself. Starting one sends a signed-out visitor to sign in (and
 * back to /interview afterwards), carrying any file they already chose.
 *
 * The user is resolved once here and handed down, so the page asks
 * `/auth/me` at most once however many buttons care who you are.
 */
export function Landing() {
  const router = useRouter();
  const { user } = useUser({ redirectTo: null });

  useEffect(() => wakeBackend(), []);

  const start = useCallback(
    (file?: File) => {
      if (file) setPendingResume(file);
      router.push(user ? destinationFor(user, "/interview") : loginHref("/interview"));
    },
    [router, user],
  );

  return (
    <>
      <SiteNav user={user} overDark onStart={() => start()} />
      <main className="flex flex-1 flex-col">
        <Hero signedIn={user !== null} onStart={start} />
        <TopicMarquee />
        <HowItWorks />
        <Grading />
        <Features />
        <Recruiters />
        <FinalCta user={user} onStart={() => start()} />
      </main>
      <SiteFooter />
    </>
  );
}
