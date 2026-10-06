---
title: Authentication and web security
topic: auth-security
license: hand-written for InterviewIQ
url:
---

# Authentication and web security

## What is the difference between authentication and authorization?

Authentication establishes who the user is — checking a password, a social
login or a token. Authorization decides what that user is allowed to do —
whether they can view this order or open the admin dashboard.

They fail differently, which is why APIs answer with different status codes:
401 when the user is not authenticated, 403 when they are authenticated but not
allowed. Mixing them up is a common source of security bugs, such as checking
that a user is logged in but not that the record they are editing belongs to them.

## How should passwords be stored?

Never store them in plain text and never encrypt them, since encryption can be
reversed. Store a hash produced by a slow, salted password hashing algorithm:
bcrypt, scrypt or Argon2. The salt is random per password, so two users with the
same password get different hashes and precomputed tables are useless; the
slowness makes guessing millions of passwords expensive.

General-purpose hashes like SHA-256 or MD5 are the wrong tool because they are
designed to be fast. Login should also avoid revealing whether an email exists:
return the same error for a wrong email and a wrong password, and take the same
time for both.

## How do server sessions and JWTs differ?

With a server session, the server stores session data and gives the browser a
random session id in a cookie. Logging out or banning a user is easy — delete
the session — but every request needs a lookup in a shared store.

A JWT is a signed token that carries the user's id and claims, so any server can
verify it with the key alone and no lookup is needed. The cost is revocation: a
stolen token stays valid until it expires. The usual compromise is a
short-lived access token plus a long-lived refresh token that can be revoked.
The token type must be checked when verifying, or a refresh token could be used
as an access token.

## How does social login with OAuth work?

The app redirects the user to the provider (Google, GitHub), the user signs in
there and approves access, and the provider redirects back with a short-lived
authorization code. The app's server exchanges that code for tokens directly
with the provider, so the tokens never pass through the browser's address bar.

PKCE adds a one-time secret that protects the code exchange, and the `state`
parameter protects against forged callbacks. Libraries such as Auth.js handle
these details and create the app's own session afterwards. Hosted services such
as Clerk take on user management entirely, trading control for less code to
maintain.

## How do you implement role-based access control in a full-stack app?

Give users roles (admin, manager, customer), give roles permissions, and check
permissions — not role names scattered through the code — at every protected
action. Deny by default: an action without an explicit rule should be refused.

The check has to happen on the server for every API route and server action,
because hiding a button in the UI does nothing to stop a direct request. In
Next.js, middleware can redirect unauthenticated users away from admin pages,
but the data-loading code and mutations must check again, since middleware alone
can be bypassed or misconfigured. Ownership checks ("is this your order?") are
as important as role checks.

## What is XSS and how do you prevent it?

Cross-site scripting happens when user-supplied text is rendered as HTML and an
attacker's script runs in another user's browser, where it can read their data
or act as them. React escapes text by default, so the risk returns mainly
through `dangerouslySetInnerHTML`, user-controlled URLs such as `javascript:`
links, and rendering markdown or rich text without sanitising it.

Defences: rely on the framework's escaping, sanitise any HTML you must render,
set a Content Security Policy, and keep session cookies `httpOnly` so a
successful script cannot read them.

## What is SQL injection and how do you prevent it?

SQL injection happens when user input is concatenated into a query string, so
input such as `' OR 1=1 --` changes the query itself. It can expose or delete
the whole database.

The fix is parameterised queries: the query and the values are sent separately,
so values can never be interpreted as SQL. ORMs such as Prisma, Eloquent and
SQLAlchemy do this automatically, but raw query helpers can still be misused if
input is placed inside the query string. Database users should also have only
the permissions the application needs.

## What is CSRF and how do you prevent it?

Cross-site request forgery tricks a logged-in user's browser into sending a
request to your site from another site; because the browser attaches cookies
automatically, the request is authenticated. It affects cookie-based
authentication, not tokens sent in a header.

Defences are `SameSite` cookies (Lax by default in modern browsers), CSRF tokens
in forms — which frameworks such as Laravel add automatically — and never
changing data on GET requests.
