"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { getAccessToken } from "@/lib/auth";

/**
 * There is no marketing page — the root just routes you to wherever you
 * belong. The check has to run in the browser because the token lives in
 * localStorage, not a cookie.
 */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace(getAccessToken() ? "/interview" : "/login");
  }, [router]);

  return (
    <div className="flex flex-1 items-center justify-center text-sm text-ink-3">
      Loading…
    </div>
  );
}
