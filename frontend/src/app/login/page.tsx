"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, login, register } from "@/lib/api";
import type { UserRole } from "@/lib/auth";
import { Button, Card, Field } from "@/components/ui";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"signin" | "register">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("candidate");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "register") {
        await register(email, password, role);
      }
      await login(email, password);
      router.replace(role === "recruiter" ? "/recruiter/sessions" : "/interview");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not reach the server",
      );
      setBusy(false);
    }
  }

  return (
    <main className="flex flex-1 items-center justify-center px-6">
      <Card className="w-full max-w-[420px] p-9">
        <form onSubmit={submit} className="flex flex-col gap-5">
          <span className="flex items-center gap-2">
            <span className="size-[22px] rounded-full bg-accent" />
            <span className="font-semibold text-ink">InterviewIQ</span>
          </span>

          <div className="flex flex-col gap-1.5">
            <h1 className="text-2xl font-semibold tracking-[-0.4px] text-ink">
              {mode === "signin" ? "Sign in" : "Create an account"}
            </h1>
            <p className="text-sm text-ink-2">
              Upload a résumé and take a skills interview, or review candidates.
            </p>
          </div>

          <Field
            label="Email"
            type="email"
            required
            autoComplete="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <Field
            label="Password"
            type="password"
            required
            minLength={8}
            autoComplete={mode === "signin" ? "current-password" : "new-password"}
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {mode === "register" && (
            <label className="flex flex-col gap-1.5">
              <span className="text-xs font-medium text-ink-2">Account type</span>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as UserRole)}
                className="rounded-[10px] border border-line bg-surface px-3.5 py-[11px] text-sm text-ink outline-none focus:border-accent"
              >
                <option value="candidate">Candidate — take interviews</option>
                <option value="recruiter">Recruiter — review candidates</option>
              </select>
            </label>
          )}

          {error && (
            <p className="rounded-[10px] bg-bad-subtle px-3.5 py-2.5 text-[13px] text-bad">
              {error}
            </p>
          )}

          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
          </Button>

          <button
            type="button"
            onClick={() => {
              setMode(mode === "signin" ? "register" : "signin");
              setError(null);
            }}
            className="text-xs text-ink-3 hover:text-ink-2"
          >
            {mode === "signin"
              ? "No account? Create one."
              : "Already have an account? Sign in."}
          </button>
        </form>
      </Card>
    </main>
  );
}
