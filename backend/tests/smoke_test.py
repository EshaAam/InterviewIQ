"""End-to-end smoke test against a running deployment.

    uv run python tests/smoke_test.py http://localhost:8000
    uv run python tests/smoke_test.py https://api.example.com \\
        --recruiter-email you@company.com --recruiter-password '...'

Runs one whole interview the way the frontend does — sign up, upload a
résumé file, wait for parsing, generate questions, answer every question,
finish, wait for grading, fetch the report and its PDF — and, given recruiter
credentials, opens the session as a recruiter. Exits non-zero on the first
thing that's wrong, so it can gate a deploy.

Each run creates a fresh candidate (smoke-<random>@example.com). With
LLM_PROVIDER=gemini it spends real tokens — run it against the fake provider
unless you mean to.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx

RESUME = (
    "Backend engineer with five years of Python and FastAPI. Designed PostgreSQL "
    "schemas, ran Redis caching and Celery workers in production, shipped with Docker."
)


class SmokeFailure(Exception):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)


def step(message: str) -> None:
    print(f"  - {message}", flush=True)  # ASCII: Windows consoles mangle anything else


def poll(fetch, done, *, what: str, timeout: float = 180.0) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        value = fetch()
        if done(value):
            return value
        if time.monotonic() > deadline:
            raise SmokeFailure(f"timed out after {timeout:.0f}s waiting for {what}: {value}")
        time.sleep(1.0)


def run(
    base: str, recruiter: tuple[str, str] | None, *, require_grounded: bool = False
) -> None:
    api = f"{base.rstrip('/')}/api/v1"
    client = httpx.Client(base_url=api, timeout=30.0)

    def ok(response: httpx.Response, *expected: int) -> httpx.Response:
        check(
            response.status_code in (expected or (200,)),
            f"{response.request.method} {response.request.url.path} → "
            f"{response.status_code}: {response.text[:300]}",
        )
        return response

    ready = client.get("/health/ready")
    check(ready.status_code == 200, f"not ready: {ready.text}")
    step("ready: postgres and redis reachable")

    email = f"smoke-{uuid.uuid4().hex[:8]}@example.com"
    password = uuid.uuid4().hex
    ok(client.post("/auth/register", json={"email": email, "password": password}), 201)
    tokens = ok(client.post("/auth/login", json={"email": email, "password": password})).json()
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    step(f"signed up as {email}")

    resume = ok(
        client.post(
            "/resumes/upload", files={"file": ("cv.txt", RESUME.encode(), "text/plain")}
        ),
        202,
    ).json()
    resume = poll(
        lambda: ok(client.get(f"/resumes/{resume['id']}")).json(),
        lambda r: r["parse_status"] in ("parsed", "failed"),
        what="resume parsing",
    )
    check(resume["parse_status"] == "parsed", f"resume parse {resume['parse_status']}")
    step(f"resume parsed: {', '.join(s['name'] for s in resume['skills'])}")

    session = ok(client.post("/sessions", json={"resume_id": resume["id"]}), 202).json()
    sid = session["id"]
    session = poll(
        lambda: ok(client.get(f"/sessions/{sid}")).json(),
        lambda s: s["state"] in ("READY", "FAILED"),
        what="question generation",
    )
    check(session["state"] == "READY", f"generation {session['state']}: {session}")
    ok(client.post(f"/sessions/{sid}/start"))
    step(f"{session['total_questions']} questions ready, interview started")

    answered = 0
    while (nxt := client.get(f"/sessions/{sid}/questions/next")).status_code == 200:
        question = nxt.json()
        ok(
            client.post(
                f"/sessions/{sid}/answers",
                json={
                    "question_id": question["id"],
                    "text": f"{question['topic']} fundamentals, tradeoffs, and production use.",
                    "time_taken_ms": 60_000,
                    "paste_events": 0,
                    "keystroke_count": 80,
                },
                headers={"Idempotency-Key": f"answer:{question['id']}"},
            ),
            202,
        )
        answered += 1
    check(nxt.status_code == 404, f"next question → {nxt.status_code}")
    ok(client.post(f"/sessions/{sid}/finish"))
    step(f"answered {answered}, finished")

    session = poll(
        lambda: ok(client.get(f"/sessions/{sid}")).json(),
        lambda s: s["state"] != "EVALUATING",
        what="grading",
    )
    check(
        session["state"] in ("COMPLETED", "NEEDS_HUMAN_REVIEW"),
        f"grading ended in {session['state']}: {session.get('failure_reason')}",
    )
    report = ok(client.get(f"/sessions/{sid}/report")).json()
    pdf = ok(client.get(f"/sessions/{sid}/report.pdf"))
    check(pdf.content.startswith(b"%PDF"), "report.pdf is not a PDF")
    step(f"graded: {session['state']}, overall {report['overall']:.2f}, PDF {len(pdf.content)} B")

    if recruiter:
        rec = httpx.Client(base_url=api, timeout=30.0)
        tokens = ok(
            rec.post("/auth/login", json={"email": recruiter[0], "password": recruiter[1]})
        ).json()
        rec.headers["Authorization"] = f"Bearer {tokens['access_token']}"
        detail = ok(rec.get(f"/recruiter/sessions/{sid}")).json()
        check(detail["candidate_email"] == email, "recruiter detail shows another candidate")
        if require_grounded:
            grounded = [q for q in detail["questions"] if q["grounded"]]
            check(bool(grounded), "RAG check failed: no generated question is grounded")
            check(
                all(q["sources"] for q in grounded),
                "RAG check failed: a grounded question has no resolved source passages",
            )
            step(f"RAG: {len(grounded)}/{len(detail['questions'])} questions have cited sources")
        ok(rec.get("/recruiter/evaluations"))
        ok(rec.get("/recruiter/costs"))
        step("recruiter: session detail, review queue and costs all load")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base_url", help="e.g. http://localhost:8000")
    parser.add_argument("--recruiter-email")
    parser.add_argument("--recruiter-password")
    parser.add_argument(
        "--require-grounded",
        action="store_true",
        help="fail unless the interview has grounded questions with resolved source passages",
    )
    args = parser.parse_args()
    recruiter = (
        (args.recruiter_email, args.recruiter_password)
        if args.recruiter_email and args.recruiter_password
        else None
    )
    if args.require_grounded and not recruiter:
        parser.error("--require-grounded needs recruiter credentials to inspect saved citations")
    print(f"Smoke test against {args.base_url}")
    started = time.monotonic()
    try:
        run(args.base_url, recruiter, require_grounded=args.require_grounded)
    except (SmokeFailure, httpx.HTTPError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"PASSED in {time.monotonic() - started:.1f}s")


if __name__ == "__main__":
    main()
