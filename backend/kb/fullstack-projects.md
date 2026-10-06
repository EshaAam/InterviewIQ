---
title: Full-stack project design
topic: fullstack-projects
license: hand-written for InterviewIQ
url:
---

# Full-stack project design

## How do you stop an online store or ERP from selling stock it does not have?

Reading the stock, checking it in application code and then writing the new
value is a race: two customers can both read "1 left" and both succeed. The check
and the update have to happen as one atomic step in the database.

The simplest version is a conditional update —
`UPDATE products SET stock = stock - 1 WHERE id = ? AND stock >= 1` — and then
checking how many rows changed; zero means it sold out. For a multi-item order,
do all the decrements inside one transaction, locking the product rows in a
consistent order (or with `SELECT ... FOR UPDATE`) so concurrent orders cannot
deadlock or oversell. Many stores reserve stock when checkout starts and release
the reservation if payment does not complete within a time limit.

## How would you design a checkout that supports several payment providers?

Keep the order logic independent of any provider. Define one interface —
create a payment, verify a payment, refund — and write an adapter per provider,
chosen by configuration or by the customer's choice. Adding a provider then means
adding an adapter, not editing checkout code.

The order has its own state (pending, paid, failed, refunded) that the
application controls. Amounts are always calculated on the server from the
database, never taken from the client. Each payment attempt carries an
idempotency key so a retried request cannot charge twice, and the order is only
marked paid after the provider confirms it.

## How should payment webhooks be handled safely?

The redirect back from a payment page is not proof of payment — a user can close
the tab, or fake the redirect. The provider's webhook, a server-to-server call,
is the source of truth.

Verify the webhook's signature with the provider's secret before trusting it.
Expect duplicates and out-of-order delivery: store the provider's event id and
ignore events already processed, and only move the order forward (a late
"pending" event must not undo "paid"). Respond quickly with 200 and do slow work
in a background job, otherwise the provider times out and retries.

## How would you build an AI shopping assistant that only recommends products in stock?

The model must not recommend from its own memory, because it knows nothing about
your catalogue or current stock. Instead, the assistant searches the product
database — by text or embeddings — with filters for stock and price, and passes
only those results to the model to describe and compare.

Tool calling fits this well: the model asks for `search_products(query, max_price)`
and your code runs the query, so availability comes from the database at that
moment. Product names, prices and links in the reply should come from the
retrieved records rather than the model's text, and stock still has to be checked
again at checkout, because it can change during the conversation.

## How do you model inventory, sales and transactions in a database?

Start from an ERD of the core entities: products, warehouses, customers, orders,
order items, payments and suppliers. Order items store a snapshot of the price
and product name at the time of sale, so later price changes do not rewrite past
invoices.

For stock, a single quantity column is simple but loses history. Recording every
change as a stock movement — received, sold, returned, adjusted, with a reason
and a user — makes the quantity auditable and explainable, and the current level
can be kept in a summary column updated in the same transaction. Money is stored
as integers in the smallest unit or as fixed-point decimals, never as floats.

## How do you turn business requirements into an SRS and a working system?

Talk to the people who will use it and watch how they work today, because the
real process often differs from the one they describe. Write the requirements
down: functional requirements as use cases ("a store manager records a goods
receipt"), non-functional ones such as performance, security and audit needs,
and the roles involved.

From that, build the data model (ERD) and clickable prototypes, for example in
Figma, and review them with stakeholders before writing much code — changing a
prototype is far cheaper than changing a database. Then deliver an MVP of the
most valuable flows, demonstrate it, and adjust based on feedback.

## How do you build an admin dashboard with sales analytics without slowing the app?

Run aggregations in the database, not in application code: `SUM` and `GROUP BY`
over indexed columns such as order date and status. For heavier reports,
pre-compute daily totals into a summary table, updated by a scheduled job or when
orders change, so the dashboard reads a few rows instead of scanning every order.

Cache dashboard data and revalidate it when the underlying data changes, paginate
tables such as recent orders, and keep the dashboard's queries from competing with
customer traffic — a read replica helps at larger scale. Check the slow queries
with `EXPLAIN` instead of guessing.

## How do you design an asynchronous processing pipeline that can be retried safely?

Accept the request, save the work as a database row, put a job on a queue and
return `202 Accepted` immediately; a worker does the slow part, such as calling
an AI model, and the client polls or receives an update when it finishes.

Queues usually deliver a job at least once, so every step must be idempotent:
check whether the result already exists before doing the work, and back that up
with a unique constraint so a duplicate run cannot write a second result. Model
the progress as explicit states with allowed transitions, retry temporary
failures with backoff, and record a clear failure reason when retries run out
rather than leaving the work stuck.
