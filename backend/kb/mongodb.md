---
title: MongoDB
topic: mongodb
license: hand-written for InterviewIQ
url:
---

# MongoDB

## When would you choose MongoDB over a relational database?

MongoDB stores JSON-like documents, so data that is naturally nested — a blog
post with its tags and metadata, a product with variable attributes — can be
read and written as one unit without joins. Its flexible schema helps when the
shape of records genuinely varies or changes quickly.

A relational database is the better default when data is highly connected and
consistency across many records matters: orders, payments, inventory and
accounting. Joins, foreign keys and mature transactions do that work for you.
The honest answer is to choose by access pattern and consistency needs, not by
what is fashionable — and "schemaless" usually means the schema moves into the
application code instead of disappearing.

## When should related data be embedded and when referenced?

Embed when the child data is read together with the parent, belongs only to it,
and stays small — the line items of an order, the address of a user. One read
returns everything and an update to the document is atomic.

Reference (store an id and look it up) when the related data is shared by many
documents, is updated independently, or can grow without limit. Comments on a
popular post are the classic case: embedding them makes the document grow
forever and eventually hit the 16 MB document limit. A middle ground is to embed
a small summary, such as the latest three comments, and reference the rest.

## How do indexes work in MongoDB?

Like most databases, MongoDB uses B-tree indexes; without one, a query scans
every document in the collection. The `_id` field is indexed automatically, and
other fields need explicit indexes for the queries the application actually runs.

For compound indexes the field order matters. A useful rule is equality fields
first, then the sort field, then range fields. `explain("executionStats")` shows
whether a query used an index and how many documents it examined compared with
how many it returned; a large gap means the index is missing or unsuitable.
Every index slows down writes and uses memory, so unused ones should be dropped.

## What is the aggregation pipeline?

The aggregation pipeline processes documents through a list of stages, each
taking the output of the previous one: `$match` filters, `$group` computes
totals, `$sort` and `$limit` order and trim, `$project` reshapes, and `$lookup`
joins another collection. Sales totals per month or the top products by revenue
are typical uses.

Putting `$match` as early as possible lets it use an index and shrinks the data
the later stages handle. `$lookup` works but is not as efficient as a join in a
relational database; if most queries need it, the data model may be better
served by embedding or by a relational database.

## Does MongoDB support transactions?

A write to a single document is always atomic, which is one reason to embed data
that changes together. Since version 4.0 MongoDB also supports multi-document
transactions on replica sets, so several writes across collections can commit or
roll back together.

They cost more than single-document writes and have time limits, so a design
that needs them everywhere is a sign the data fits a relational model better.
Write concern controls durability: `w: "majority"` waits until most replica
members have the write, so it survives a primary failing.

## What does Mongoose add on top of the MongoDB driver?

Mongoose adds schemas and models to MongoDB in Node.js: field types, required
fields, defaults and validation, so bad data is rejected before it is saved. It
also provides middleware hooks, such as hashing a password before save, and
helpers for common queries.

`populate()` replaces stored ids with the referenced documents, which looks like
a join but runs extra queries from the application. Populating inside a loop
recreates the N+1 problem. Using `.lean()` for read-only queries returns plain
objects instead of full Mongoose documents and is noticeably faster.
