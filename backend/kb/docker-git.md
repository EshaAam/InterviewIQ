---
title: Docker, Git and CI
topic: docker-git
license: hand-written for InterviewIQ
url:
---

# Docker, Git and CI

## What is the difference between a Docker image and a container?

An image is a read-only template: a filesystem with the application, its
dependencies and the command to run, built from a Dockerfile. A container is a
running instance of an image with its own writable layer, process space and
network. Many containers can run from one image, and stopping a container does
not change the image.

The practical consequence is that anything written inside a container is lost
when it is removed. Data that must survive — database files, uploads — belongs
in a volume.

## How do Docker layers and build caching work?

Each instruction in a Dockerfile creates a layer, and Docker reuses a cached
layer when the instruction and its inputs have not changed. Once one layer
changes, every layer after it is rebuilt.

That is why dependency manifests are copied and installed before the source
code: `COPY package.json package-lock.json`, `RUN npm ci`, then `COPY . .`.
Editing application code then reuses the expensive install layer. A
`.dockerignore` keeps `node_modules`, `.git` and local env files out of the
build context, which makes builds faster and stops secrets ending up in the image.

## What are multi-stage builds for?

A multi-stage Dockerfile uses one stage with compilers and build tools to
produce the application, then copies only the result into a small final image.
For a Next.js app, the build stage installs all dependencies and runs
`next build`; the final stage contains the built output and production
dependencies only.

The final image is smaller, faster to pull and has less installed software for
an attacker to use. Running as a non-root user in the final stage is another
easy hardening step.

## What is the difference between named volumes, bind mounts and anonymous volumes?

A named volume is storage managed by Docker that outlives containers — the right
home for a database. A bind mount maps a folder from the host into the
container, which suits development because code edits appear immediately.

An anonymous volume is created without a name, often to stop a bind mount from
hiding a folder that the image prepared, such as installed dependencies. It
survives a rebuild of the image, so after adding a dependency the container can
keep using the old installed packages. Recreating it — with
`docker compose up --build --renew-anon-volumes` — fixes that.

## How does Docker Compose help in development?

Compose describes several containers — API, worker, database, Redis — in one
file and starts them together. Services reach each other by service name, so the
API connects to `db:5432` instead of an IP address.

`depends_on` alone only controls start order; it does not wait for the database
to be ready. Adding a healthcheck to the database and `condition: service_healthy`
to its dependants makes the API wait until Postgres actually accepts
connections. Environment variables come from an env file that is not committed.

## What is the difference between git merge and git rebase?

Merge joins two branches with a merge commit and keeps the history exactly as it
happened. Rebase replays your commits on top of the other branch, giving a
straight line of history as if you had started from the latest code.

Rebase rewrites commit ids, so it should only be used on your own branch before
others have based work on it. Never rebase a shared branch such as `main`. A
common workflow is to rebase a feature branch onto the latest main to resolve
conflicts locally, then merge it through a pull request.

## How do you undo mistakes in Git?

`git revert <commit>` creates a new commit that reverses an earlier one; it is
safe on shared branches because history is not rewritten. `git reset` moves the
branch pointer backwards — `--soft` keeps the changes staged, `--hard` discards
them — and should only be used on commits that have not been pushed.

`git reflog` lists where the branch has pointed recently, so even commits lost
after a hard reset can usually be recovered. `git restore` discards changes to a
file that have not been committed yet.

## What should a CI pipeline check?

On every push or pull request: lint, type-check, run the tests, and build the
application, ideally the same production image that will be deployed. Jobs that
do not depend on each other should run in parallel so feedback is quick, and a
pull request should not be mergeable until the required checks pass.

Tests that need real services, such as database migrations, can start a
Postgres service container in the job. Secrets belong in the CI provider's
secret store, never in the workflow file.
