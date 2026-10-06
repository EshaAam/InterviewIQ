---
title: Node.js, Express and Prisma
topic: nodejs
license: hand-written for InterviewIQ
url:
---

# Node.js, Express and Prisma

## How does Node.js handle many requests with a single thread?

JavaScript in Node runs on one thread, driven by the event loop. Slow operations
— network calls, database queries, file reads — are started and handed off; the
thread moves on to other requests and comes back when the result is ready. That
is why one Node process can hold thousands of open connections.

Under the hood, libuv uses the operating system's non-blocking networking and a
small thread pool for work that has no non-blocking API, such as file system
access, DNS lookups and some crypto. The weakness is CPU-heavy work: hashing a
large file or a tight loop in JavaScript blocks the single thread, and every
other request waits. Such work belongs in `worker_threads`, a separate process,
or a job queue.

## How does Express middleware work?

A middleware is a function `(req, res, next)` that runs in the order it was
registered. It can read or modify the request, end the response, or call
`next()` to pass control to the next function. Logging, body parsing,
authentication and CORS are all middleware, and routes are effectively the last
middleware in the chain.

Order matters: a body parser registered after a route will not have run when
that route executes. Error-handling middleware is recognised by having four
arguments, `(err, req, res, next)`, and must be registered after the routes.
Calling `next(err)` skips ordinary middleware and jumps to it.

## How should errors in async route handlers be handled in Express?

Express 4 does not catch rejected promises. If an `async` handler throws, the
error never reaches the error middleware and the request hangs until it times
out. The fix is to catch and call `next(err)`, usually through a small wrapper
that every async route uses. Express 5 forwards rejected promises automatically.

A central error handler then turns errors into consistent responses: known
errors such as validation failures become 400 or 404 with a message, and
unexpected errors become a 500 with a generic message, while the details are
logged. Stack traces should never be sent to the client in production.

## How would you structure a REST API in Express?

Split it by responsibility: routers declare the paths, controllers handle HTTP —
read the request, call the service, choose the status code — and services hold
the business logic without knowing anything about HTTP. Data access sits behind
the services. This keeps business rules testable without starting a server and
reusable from a background job.

Validate request bodies at the edge with a schema library, use plural resource
nouns (`/orders/:id`) with HTTP methods for the action, return the right status
codes (201 on create, 404 when missing), and paginate list endpoints instead of
returning everything.

## What is Prisma, and how does it compare with writing SQL?

Prisma is a TypeScript ORM. The data model lives in `schema.prisma`; from it
Prisma generates migrations and a fully typed client, so `prisma.order.findMany`
returns objects whose types match the schema and a renamed column becomes a
compile error rather than a runtime surprise.

The trade-off is control. Complex reporting queries are clearer in SQL, which
Prisma supports through `$queryRaw` with parameters. Relations are loaded with
`include` or `select`; fetching orders and then their items one by one in a loop
recreates the N+1 problem, while one `include` loads them in a single query.
`prisma.$transaction` groups writes so they succeed or fail together.

## How do Prisma migrations work in development and production?

`prisma migrate dev` compares the schema with the database, generates a SQL
migration file, applies it and regenerates the client. It is for development
only, because it may reset the database when it detects drift.

`prisma migrate deploy` only applies migration files that are already committed
and never generates new ones or resets anything, which is what a deployment
should run. The migration files belong in version control and should be reviewed
like code, since a generated migration can drop a column that still holds data.

## When would you use WebSockets instead of polling?

A WebSocket starts as an HTTP request that is upgraded to a persistent
two-way connection, so the server can push messages the moment something
happens. That suits chat, live notifications, collaborative editing and
multiplayer features, where polling would either be slow or waste requests.

They bring costs. Each open connection holds server memory, so scaling across
several servers needs a shared channel such as Redis pub/sub to deliver a
message to whichever server holds the user's connection. Connections drop, so
clients need reconnection with backoff and heartbeats to detect dead sockets.
For updates every few seconds or only from server to client, polling or
Server-Sent Events are simpler and often enough.
