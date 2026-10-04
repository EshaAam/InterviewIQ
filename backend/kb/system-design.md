---
title: System design
topic: system-design
license: hand-written for InterviewIQ
url:
---

# System design

## Queues and asynchronous work

A request that takes thirty seconds cannot be served synchronously. The client
times out, a proxy may cut the connection, and if it drops the work is lost with
no record it was ever attempted.

The pattern is to persist the intent, hand a job to a broker, and return
immediately:

```
POST /sessions  ->  write the row, enqueue the job, return 202 Accepted
                    worker picks the job up, does the slow part
client polls GET /sessions/{id} until the state changes
```

Three things this buys. The response is fast and predictable. The work survives
a dropped connection, because it lives in the broker rather than in the request.
And workers scale separately from the API — a backlog is solved by adding
workers, not web servers.

The costs are a broker to operate, a second process to deploy, and a client that
must now handle "accepted but not finished". That last one is a UI problem as
much as a backend one.

**Commit before you enqueue.** The worker is a different connection: if the job
is published before the transaction commits, a fast worker can look for the row,
find nothing, and drop the job.

## Delivery guarantees and idempotency

Message brokers offer:

- **At-most-once** — acknowledge on receipt. A crash mid-processing loses the
  message.
- **At-least-once** — acknowledge after processing. A crash mid-processing means
  redelivery, so a message can be handled more than once.
- **Exactly-once** — not achievable end to end in a distributed system. What
  systems sell under that name is at-least-once delivery plus deduplication at
  the consumer.

At-least-once is the usual choice, and it pushes a requirement onto you: **the
handler must be idempotent.** Running it twice must not charge the card twice or
write a second row.

Idempotency is normally enforced with a uniqueness constraint rather than a
check — a check-then-insert has a race between the two. Insert and let the
database reject the duplicate:

```sql
UNIQUE (question_id, idempotency_key)
```

Celery's `acks_late=True` is this trade made explicit: acknowledge after the
task completes so a killed worker causes redelivery rather than loss, and accept
that tasks can run twice.

## Caching

Cache what is read far more often than written, expensive to compute, and
tolerant of being slightly stale. Those three conditions together — a cheap
query cached aggressively buys nothing but a staleness bug.

The hard part is invalidation, and it should be decided before the cache is
added:

- **TTL** — expire after a fixed period. Simple, and bounded staleness.
- **Write-through / explicit invalidation** — update or delete the entry when
  the source changes. Fresher, but every write path must remember.
- **Versioned keys** — include a version in the key so a bump invalidates
  everything at once, with no deletion.

Failure modes worth naming. A **stampede**: a popular key expires and a thousand
requests recompute it simultaneously — mitigated by a lock or by serving stale
while one request refreshes. **Cache penetration**: repeated misses for a key
that does not exist, fixed by caching the negative result.

A cache should be an optimisation, never a dependency. If the cache being down
turns into an outage rather than a slowdown, it has become part of the critical
path.

## Horizontal and vertical scaling

**Vertical** — a bigger machine. Simple, needs no code changes, and the fastest
answer when it works. It has a hard ceiling, usually costs superlinearly at the
top end, and leaves a single point of failure.

**Horizontal** — more machines behind a load balancer. No ceiling in principle
and it provides redundancy, but it requires the application to be **stateless**
(or to share state deliberately), and it introduces everything distributed
systems bring: partial failure, consistency questions, and harder debugging.

Statelessness is the real prerequisite. In-memory session data, a local upload
directory, or a per-process scheduler all break the moment a second instance
exists. That is why uploads go to object storage, sessions go to a shared store
or a signed token, and a scheduler has to be a singleton — two Celery beat
processes dispatch every scheduled job twice.

## Circuit breakers

When a dependency is failing, continuing to call it makes things worse: every
request waits for a timeout, threads or connections pile up, and the failure
spreads upward.

A circuit breaker tracks consecutive failures. Past a threshold it **opens** and
fails immediately without attempting the call. After a cooldown it goes
**half-open** and lets a single request through to probe recovery — success
closes it, failure re-opens it.

The value is failing in microseconds instead of stacking thirty-second timeouts
across every worker. It converts a slow, resource-consuming failure into a fast,
cheap one, which is what keeps the rest of the system responsive.

It composes with retries, and the order matters: the breaker belongs *outside*
the retry, or retries keep hammering a dependency that is already known to be
down.

## Retries and backoff

Retry only what might succeed on a second attempt — a timeout, a 5xx, a 429.
Retrying a 400 just adds load.

Use **exponential backoff with jitter**. Backoff gives the dependency room to
recover; jitter is not decoration. Without it, every client that failed at the
same instant retries at the same instant, recreating the overload that caused
the failure. That is the thundering-herd problem, and a small random offset
solves it.

Cap the attempts and have a terminal path — a dead-letter queue, a failure state
on the row — so work that will never succeed stops consuming capacity and
becomes visible instead of silently vanishing.

## Rate limiting

Protects a service from overload and from one client monopolising it.

- **Fixed window** — count per client per interval. Trivial, but allows a double
  burst across a boundary: a client can spend its whole quota at the end of one
  window and again at the start of the next.
- **Sliding window** — smooths that boundary at the cost of more bookkeeping.
- **Token bucket** — tokens refill at a steady rate up to a capacity; each
  request spends one. Allows a controlled burst while bounding the sustained
  rate, which usually matches what people actually want.

Respond with `429 Too Many Requests` and a `Retry-After` header. Without it a
well-behaved client cannot do better than guess, and will usually guess badly.

The counter lives in shared storage — Redis, typically — because a per-instance
counter means the real limit is the configured one multiplied by the instance
count.

## Read replicas

A replica takes a copy of the primary's writes and serves reads. It helps when
the workload is read-heavy, and it does nothing for write throughput — every
write still goes to the primary.

The cost is **replication lag**. A replica is behind by milliseconds to seconds,
so a user who writes and immediately reads can see their own change missing.
That specific case has a name, read-your-writes, and the usual fix is to route a
user's reads to the primary for a short window after they write.

Lag also means a failover can lose the most recent transactions unless
replication is synchronous — and synchronous replication makes every write wait
for the replica, trading throughput for durability.

## CAP

In the presence of a network **partition**, a distributed system must choose
between **consistency** (every read sees the latest write) and **availability**
(every request gets a non-error response).

The common misreading is "pick two of three". Partition tolerance is not
optional in a distributed system — networks partition, and a system that cannot
tolerate that simply breaks. The real choice is what to do *during* a partition:

- **CP** — refuse requests on the minority side rather than serve stale data.
  A bank balance.
- **AP** — serve what you have and reconcile later. A shopping cart, a social
  feed.

CAP also only describes behaviour during a partition. The rest of the time the
relevant trade-off is latency against consistency, which is what PACELC adds:
else, choose between latency and consistency.

## Observability

Three signals, answering different questions.

**Metrics** are cheap aggregates — request rate, error rate, latency
percentiles, queue depth — good for alerting and dashboards. Alert on symptoms
users feel (error rate, p99 latency) rather than causes (CPU), which produce
noise.

**Logs** are discrete events with context. Structured logs with a correlation ID
let you reconstruct one request across services; unstructured ones leave you
grepping.

**Traces** follow a single request through every service, which is the only
practical way to find where latency actually went in a distributed call graph.

Percentiles, not averages. A mean latency of 100 ms hides a p99 of 4 seconds,
and the p99 is the experience that makes people leave. For cost and capacity,
measure the thing that is actually scarce — in an LLM pipeline that is tokens
and provider rate limits, not CPU.
