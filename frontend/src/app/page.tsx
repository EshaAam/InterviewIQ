"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { me } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { homeFor } from "@/lib/use-user";
import { Spinner } from "@/components/ui";

/**
 * There is no marketing page — the root just routes you to wherever you
 * belong. The check has to run in the browser because the token lives in
 * localStorage, not a cookie, and "where you belong" depends on your role,
 * which only `GET /auth/me` can tell us.
 */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let cancelled = false;
    me()
      .then((user) => {
        if (!cancelled) router.replace(homeFor(user));
      })
      .catch(() => {
        clearTokens();
        if (!cancelled) router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="flex flex-1 items-center justify-center">
      <Spinner />
    </div>
  );
}
