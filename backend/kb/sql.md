---
title: SQL and PostgreSQL
topic: sql
license: hand-written for InterviewIQ
url:
---

# SQL and PostgreSQL

## Indexes: what they buy and what they cost

An index is an ordered structure (a B-tree, by default) that lets the planner
find matching rows without reading the whole table. A lookup goes from O(n) to
roughly O(log n), which on a million-row table is the difference between a
sequential scan and a handful of page reads.

The costs are real and often ignored:

- **Writes get slower.** Every insert, update and delete must maintain every
  index on the table. A table with eight indexes pays eight times on write.
- **Storage grows.** An index on a wide column can approach the size of the
  table itself.
- **It only helps if the query can use it.** This is the part that surprises
  people.

An index on `(a, b)` serves `WHERE a = ?` and `WHERE a = ? AND b = ?`, but not
`WHERE b = ?` — the leading column has to be constrained. Wrapping a column in a
function defeats it too: `WHERE lower(email) = ?` cannot use an index on
`email`, though it can use an expression index on `lower(email)`.

## The N+1 query problem

Fetch a list with one query, then loop over it issuing another query per row.
A hundred rows become a hundred and one round trips.

```python
sessions = await db.scalars(select(InterviewSession))
for session in sessions:
    user = await db.get(User, session.user_id)   # one query per session
```

The cost is latency, not CPU. Each query may take a millisecond, but a hundred
sequential round trips is a hundred milliseconds of pure waiting, and it scales
linearly with the result set — so it looks fine in development against ten rows
and falls over in production.

The fix is to fetch the related data up front: a `JOIN`, or an ORM eager load
such as SQLAlchemy's `selectinload`/`joinedload`. `selectinload` issues one
extra query for the whole batch; `joinedload` folds it into the original query.

## INNER JOIN and LEFT JOIN

`INNER JOIN` returns only rows with a match on both sides. `LEFT JOIN` returns
every row from the left table, filling the right side with `NULL` where there is
no match.

The trap is filtering:

```sql
SELECT u.*, s.state
FROM users u
LEFT JOIN sessions s ON s.user_id = u.id
WHERE s.state = 'COMPLETED';     -- this is now an INNER JOIN
```

The `WHERE` runs after the join and discards the `NULL` rows the `LEFT JOIN`
just produced, silently turning it into an inner join. To keep them, move the
condition into the join:

```sql
LEFT JOIN sessions s ON s.user_id = u.id AND s.state = 'COMPLETED'
```

## Transactions and isolation levels

An isolation level controls what one transaction can see of another's
uncommitted or concurrent work. The classic anomalies, in increasing difficulty:

- **Dirty read** — seeing another transaction's uncommitted changes.
- **Non-repeatable read** — reading a row twice and getting different values,
  because another transaction committed in between.
- **Phantom read** — re-running a range query and finding new rows.

PostgreSQL defaults to `READ COMMITTED`, which prevents dirty reads but allows
the other two. `REPEATABLE READ` gives a consistent snapshot for the whole
transaction. `SERIALIZABLE` behaves as though transactions ran one at a time.

Stricter is not free: PostgreSQL implements the stricter levels optimistically,
so a conflict surfaces as a serialization failure the application has to catch
and retry. Choosing `SERIALIZABLE` means committing to that retry loop.

## SELECT ... FOR UPDATE

`SELECT ... FOR UPDATE` takes a row-level lock on everything it returns, held
until the transaction ends. Other transactions trying to lock or update those
rows wait.

It exists for read-modify-write races:

```sql
BEGIN;
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
-- no other transaction can modify this row now
UPDATE accounts SET balance = balance - 100 WHERE id = 1;
COMMIT;
```

Without the lock, two concurrent transactions can both read the old balance and
both write, losing one update.

The risk is deadlock. Two transactions that lock the same rows in opposite
orders will each wait for the other; PostgreSQL detects this and kills one.
Locking rows in a consistent order — always ascending by primary key — avoids
it. `FOR UPDATE SKIP LOCKED` is the variant that makes a queue table work:
each worker claims rows nobody else holds instead of waiting.

## Normalisation, and when to stop

Normalising means storing each fact once. The payoff is that an update touches
one row, which eliminates a class of anomalies:

- **Update anomaly** — the same fact duplicated in ten rows, and an update that
  catches nine of them.
- **Insertion anomaly** — being unable to record a fact because some unrelated
  required column has no value yet.
- **Deletion anomaly** — losing a fact as a side effect of deleting something
  else that happened to carry it.

Denormalisation is the deliberate reverse, trading those risks for read speed:
a cached count, a duplicated display name, a materialised view. It is a valid
choice when reads dominate and the duplicate has a clear owner and refresh path.
It is a bug when it happens by accident.

## Reading an EXPLAIN plan

`EXPLAIN` shows the planner's intended strategy; `EXPLAIN ANALYZE` runs the
query and reports what actually happened. Things worth looking at, in order:

**Scan type.** A `Seq Scan` on a large table where an index exists means the
index was not usable — or the planner judged a scan cheaper, which is often
correct for a query returning most of the table.

**Estimated versus actual rows.** This is the highest-value signal. If the
planner expects 10 rows and gets 100,000, every decision above that node was
made on bad information, and the usual cause is stale statistics — `ANALYZE`
the table.

**Where the time goes.** Nested loops are fine over small inputs and
catastrophic over large ones. A sort spilling to disk (`external merge`) means
`work_mem` is too small for the query.

## Connection pooling

Opening a PostgreSQL connection is expensive: a TCP handshake, authentication,
and a new backend *process* on the server. Doing that per request adds
milliseconds and puts the server under process-creation load.

A pool keeps a set of established connections and hands them out. It does two
things:

1. **Reuse** — amortises the setup cost across many requests.
2. **Bounding** — caps how many connections exist at once. PostgreSQL has a hard
   `max_connections`, and each backend costs memory, so an unbounded client is a
   denial of service against your own database.

A pool is not a cache: it stores connections, not results. `pool_pre_ping`
issues a cheap `SELECT 1` before handing out a connection, which costs a round
trip and prevents the "server closed the connection unexpectedly" error after a
restart or an idle timeout killed a pooled socket.

## Migrations

A schema change has to be repeatable and reversible, which is what a migration
tool such as Alembic provides: an ordered chain of revisions, each with an
`upgrade` and a `downgrade`.

Autogenerate compares the models to the database and writes a candidate
revision. It is a draft, not an answer — it misses data migrations entirely, and
it can propose destructive operations.

Adding a `NOT NULL` column to a populated table needs a default for the existing
rows:

```python
op.add_column(
    "evaluations",
    sa.Column("needs_review", sa.Boolean(), nullable=False, server_default=sa.false()),
)
```

The `server_default` exists for the backfill; the application still sets the
value explicitly on insert.

## Keys and UUIDs

A sequential integer key is compact and indexes well, but it leaks information:
`/orders/41` tells a visitor roughly how many orders exist, and it invites
enumeration.

A UUID primary key avoids both and can be generated by the client before any
database round trip — which matters when an identifier must be known in advance,
such as enqueueing a background job for a row that has not been inserted yet.

The costs are size (16 bytes against 4 or 8) and, for random UUIDv4 keys, poor
index locality: inserts land in random positions in the B-tree instead of
appending at the end. UUIDv7, which is time-ordered, restores the locality while
keeping the other properties.
