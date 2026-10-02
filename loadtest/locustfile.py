"""Load test: candidates taking whole interviews, concurrently.

Run against a stack on the **fake** provider (real models cost money and rate-
limit long before the system does), with FAKE_LATENCY_MS set so each "model
call" takes model-like time:

    uvx locust -f loadtest/locustfile.py --host http://localhost:18000 \\
        --headless -u 20 -r 2 -t 3m --csv loadtest/results/run

Locust is run with `uvx`, so it never becomes a project dependency.

Two kinds of numbers come out:
- HTTP endpoints (`POST /sessions`, `GET /sessions/:id`, ...): how fast the API
  answers. These should stay flat — every slow thing is in a worker.
- `pipeline: …` rows (custom events): wall-clock time from asking for work to
  seeing it done — résumé → parsed, session → READY, finish → graded. These are
  what a candidate feels, and they grow when the worker queue backs up.
"""

from __future__ import annotations

import time
import uuid

from locust import HttpUser, between, events, task

API = "/api/v1"
RESUME = "Backend engineer: python, fastapi, postgresql, redis, docker and celery in production."


class Candidate(HttpUser):
    # Think time between interviews, as a real person would have.
    wait_time = between(1, 3)

    def on_start(self) -> None:
        email = f"load-{uuid.uuid4().hex[:10]}@example.com"
        password = "load-test-password"
        self.client.post(f"{API}/auth/register", json={"email": email, "password": password})
        token = self.client.post(
            f"{API}/auth/login", json={"email": email, "password": password}
        ).json()["access_token"]
        self.client.headers["Authorization"] = f"Bearer {token}"

    # --- helpers ---

    def _wait_for(self, name: str, url: str, done, timeout: float = 300.0) -> dict:
        """Poll until `done`, then report the whole wait as one custom event."""
        started = time.perf_counter()
        while True:
            body = self.client.get(url, name=f"GET /{url.split('/')[3]}/:id (poll)").json()
            if done(body):
                events.request.fire(
                    request_type="pipeline",
                    name=name,
                    response_time=(time.perf_counter() - started) * 1000,
                    response_length=0,
                    exception=None,
                    context={},
                )
                return body
            if time.perf_counter() - started > timeout:
                events.request.fire(
                    request_type="pipeline",
                    name=name,
                    response_time=timeout * 1000,
                    response_length=0,
                    exception=TimeoutError(f"{name} did not finish in {timeout:.0f}s"),
                    context={},
                )
                raise TimeoutError(name)
            time.sleep(1.0)

    # --- the scenario ---

    @task
    def take_an_interview(self) -> None:
        resume = self.client.post(f"{API}/resumes", json={"text": RESUME}).json()
        self._wait_for(
            "résumé → parsed",
            f"{API}/resumes/{resume['id']}",
            lambda r: r["parse_status"] in ("parsed", "failed"),
        )

        session = self.client.post(
            f"{API}/sessions", json={"resume_id": resume["id"]}
        ).json()
        sid = session["id"]
        session = self._wait_for(
            "session → READY",
            f"{API}/sessions/{sid}",
            lambda s: s["state"] in ("READY", "FAILED"),
        )
        if session["state"] != "READY":
            return

        self.client.post(f"{API}/sessions/{sid}/start", name="POST /sessions/:id/start")
        while True:
            response = self.client.get(
                f"{API}/sessions/{sid}/questions/next",
                name="GET /sessions/:id/questions/next",
                catch_response=True,
            )
            with response:
                if response.status_code == 404:
                    response.success()  # 404 here means "no questions left"
                    break
            question = response.json()
            self.client.post(
                f"{API}/sessions/{sid}/answers",
                json={
                    "question_id": question["id"],
                    "text": f"{question['topic']} fundamentals, tradeoffs, production use.",
                    "time_taken_ms": 45_000,
                    "paste_events": 0,
                    "keystroke_count": 70,
                },
                headers={"Idempotency-Key": f"answer:{question['id']}"},
                name="POST /sessions/:id/answers",
            )

        self.client.post(f"{API}/sessions/{sid}/finish", name="POST /sessions/:id/finish")
        self._wait_for(
            "finish → graded",
            f"{API}/sessions/{sid}",
            lambda s: s["state"] != "EVALUATING",
        )
        self.client.get(f"{API}/sessions/{sid}/report", name="GET /sessions/:id/report")
