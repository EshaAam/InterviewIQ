---
title: HTTP and REST
topic: http
license: hand-written for InterviewIQ
url:
---

# HTTP and REST

## Idempotency

A method is idempotent when making the same request twice leaves the server in
the same state as making it once. `GET`, `PUT` and `DELETE` are idempotent by
specification; `POST` is not, because two POSTs to a collection normally create
two resources.

Idempotency is not about the response being identical — a second `DELETE`
reasonably returns 404 — but about the *effect*.

It matters because networks fail in the worst possible way: a client sends a
request, the response is lost, and the client cannot tell whether the server
processed it. For an idempotent request the answer is simple — retry. For a
non-idempotent one, retrying risks a duplicate charge or a duplicate record.

That is what an idempotency key solves. The client generates a unique key per
logical operation and sends it as a header:

```
POST /answers
Idempotency-Key: 7f3a...
```

The server stores it with the created row under a uniqueness constraint. A
retry carrying the same key returns the original result instead of creating a
second row — which turns "the connection dropped and the mobile client retried"
from a data-corruption event into a no-op. The key must be generated **before**
the first attempt, not per attempt, or every retry gets a fresh key and the
protection is lost.

## Status code families

- **2xx success.** `200 OK`, `201 Created`, `202 Accepted` (queued, not done),
  `204 No Content`.
- **3xx redirection.** `301` permanent, `302`/`307` temporary, `304 Not
  Modified` for a successful cache revalidation.
- **4xx client error.** The request was wrong and repeating it unchanged will
  fail again: `400` malformed, `401` unauthenticated, `403` authenticated but
  not allowed, `404` absent, `409` conflicts with current state, `422` failed
  validation, `429` rate limited.
- **5xx server error.** The request may have been fine; the server failed.

The family is a contract about **retrying**. A 5xx or a 429 is worth retrying
with backoff. A 4xx other than 429 is not — the same request will fail the same
way, so a client that retries a 400 is just generating load.

`401` versus `403` is the pair most often confused: 401 means "I do not know who
you are", 403 means "I know, and you may not".

## PUT versus PATCH

`PUT` replaces the resource with the representation sent. Fields omitted from
the body are omitted from the resource — a common source of accidental data
loss when a client sends a partial object to a `PUT`.

`PATCH` applies a partial modification; only the included fields change.

`PUT` is idempotent because sending the same full representation twice leaves
the same state. `PATCH` **depends on the patch**: setting a field to a value is
idempotent, incrementing a counter is not. Treating all PATCHes as idempotent is
a mistake worth avoiding.

## CORS

The browser's same-origin policy stops a page on one origin from reading
responses from another. CORS is how a server opts into being read.

The server sends `Access-Control-Allow-Origin` and friends; the browser enforces
the result. Two consequences follow:

- **It is browser-only.** `curl` and a server-side HTTP client ignore CORS
  entirely. It is not an access control — it protects the user's browser
  session, not your API.
- **The request often still happens.** For "simple" requests the browser sends
  it and then blocks the *response* if the headers do not permit it.

Anything beyond a simple request — a custom header such as `Authorization` or
`Idempotency-Key`, a `PUT`, a JSON content type — triggers a **preflight**: an
`OPTIONS` request the browser sends first to ask whether the real one is
allowed. A preflight that fails produces an error with no useful detail in the
console, which is why a missing `Access-Control-Allow-Headers` entry is such a
reliable time sink. The response is cacheable via `Access-Control-Max-Age`.

`Access-Control-Allow-Origin: *` cannot be combined with credentials; a
credentialed request requires an explicit origin.

## Caching

Two mechanisms, used together.

**Freshness** — `Cache-Control: max-age=3600` lets a client reuse a response for
an hour without asking. `no-store` forbids storing it at all; `no-cache` permits
storing but requires revalidation before reuse.

**Validation** — when a cached copy goes stale, the client revalidates instead
of refetching. The server sent an `ETag` (a content fingerprint) or a
`Last-Modified` date; the client echoes it back as `If-None-Match` or
`If-Modified-Since`. If nothing changed the server answers `304 Not Modified`
with **no body**, which saves the bandwidth while confirming freshness.

`Vary` tells caches which request headers change the response — `Vary: Accept-
Encoding`, or `Vary: Authorization` for anything user-specific. Omitting it on a
personalised response is how one user's data gets served to another from a
shared cache.

## Cookies versus bearer tokens

**Cookies** are attached automatically by the browser to every matching request.
That convenience is exactly the CSRF problem: another site can cause the
browser to send an authenticated request. The mitigations are `SameSite=Lax` or
`Strict` (now the browser default), and anti-CSRF tokens. An `httpOnly` cookie
cannot be read by JavaScript, so XSS cannot steal it.

**Bearer tokens** must be attached explicitly by your own code, so CSRF does not
apply. But a token in `localStorage` is readable by any script on the origin,
which makes any XSS a token theft.

Neither is strictly safer; they fail differently. httpOnly cookies with
`SameSite` are the stronger default for a browser app. Bearer tokens suit
non-browser clients and cross-origin APIs, where cookies are awkward anyway.

Short access-token lifetimes limit the damage of a stolen token, with a
long-lived refresh token to avoid constant re-login. The refresh token must be
distinguishable from the access token — typically a `type` claim checked at
verification — or a stolen refresh token works everywhere an access token does
and the short lifetime bought nothing.

## HTTP/2 and HTTP/3

HTTP/1.1 allows one outstanding request per connection, so browsers opened six
or so per origin and developers worked around the limit: concatenating assets,
sprite sheets, sharding across subdomains.

**HTTP/2 multiplexes** many concurrent streams over a single TCP connection, and
compresses headers with HPACK. That removes head-of-line blocking at the HTTP
layer and makes the old workarounds counterproductive — domain sharding now
costs extra connections and handshakes for no benefit, and bundling everything
into one file defeats granular caching.

Head-of-line blocking remains at the **TCP** layer: one lost packet stalls every
stream on that connection, because TCP delivers bytes in order. HTTP/3 fixes
that by moving to QUIC over UDP, where each stream is independently ordered.

## REST and statelessness

Stateless means each request carries everything needed to process it; the server
keeps no per-client session context between requests.

It does **not** mean the server stores no data. The database is application
state and is entirely expected — what is excluded is *conversational* state, the
server remembering where this particular client was in a multi-step flow.

The payoff is operational: any instance can serve any request, so a load
balancer needs no sticky sessions, instances can be added or killed freely, and
a restart loses nothing. That is the property that makes horizontal scaling
straightforward.

In practice authentication is where this is decided. A server-side session table
keyed by a cookie is stateful by this definition — workable, but it needs shared
storage. A signed token carrying the claims is stateless: any instance can
verify it with the key alone. The trade-off is revocation, which a stateless
token cannot do without reintroducing a lookup.
