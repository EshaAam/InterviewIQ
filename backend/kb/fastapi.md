---
title: FastAPI
topic: fastapi
license: hand-written for InterviewIQ
url:
---

# FastAPI

## Dependency injection

`Depends(f)` tells FastAPI: before running this handler, call `f`, and pass me
what it returns. FastAPI resolves the whole tree — dependencies of dependencies
— before the handler body runs.

```python
async def get_current_user(db: AsyncSession = Depends(get_db), token: str = Depends(oauth2)):
    ...

@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return user
```

The property that catches people out is **per-request caching**. Within one
request each dependency is called once and its result reused, so a handler and
a `get_current_user` that both depend on `get_db` receive the *same* session
object — and therefore the same transaction. Relying on that is what makes
"read the user, then write a row" atomic without passing the session around by
hand.

`Annotated[AsyncSession, Depends(get_db)]` is the modern spelling. Aliasing it
(`DbSession = Annotated[...]`) keeps handler signatures readable.

## Dependencies with yield

A dependency that yields runs setup before the handler and teardown after:

```python
async def get_db():
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

The teardown runs whether the handler returned or raised, which makes this the
natural place for a transaction boundary: one request, one transaction. A
handler that raises — a 404, a constraint violation, a bug — rolls back
everything, and no handler needs to call `commit` itself.

Service code inside such a request calls `flush`, not `commit`. `flush` sends
the pending SQL so generated keys are populated and constraints fire, while
leaving the transaction open and still rollback-able.

## Path operation functions: async def or def

`async def` handlers run directly on the event loop. Plain `def` handlers are
run in a threadpool, so a blocking call inside one cannot stall the loop.

The dangerous combination is blocking work inside `async def`. A synchronous
database driver or a `requests` call there blocks the single event loop thread,
and every other in-flight request waits — including ones that have nothing to do
with the slow endpoint. The symptom is latency appearing in unrelated routes.

Rule of thumb: if the libraries you call are async, use `async def`. If they are
blocking and you cannot change them, plain `def` is safer than `async def` plus
a blocking call. `asyncio.to_thread` covers the case where one blocking call
sits inside otherwise-async code.

## Response models

`response_model` does more than document:

```python
@router.post("/register", response_model=UserRead, status_code=201)
async def register(...) -> UserRead:
    ...
```

FastAPI validates the returned object against the model and **filters it** to
the declared fields. Returning a SQLAlchemy `User` with a `hashed_password`
column through a `UserRead` that does not declare one strips the hash
structurally — not because the handler remembered to, but because the field does
not exist on the response model.

That makes it a security control, not decoration. It also generates the OpenAPI
schema, which is why `/docs` stays accurate for free.

`model_config = ConfigDict(from_attributes=True)` is what lets a Pydantic model
read attributes off an ORM object instead of requiring a dict.

## Validation happens before the handler

A request body is parsed and validated against its Pydantic model before the
handler is entered. A malformed body never reaches handler code: FastAPI returns
`422 Unprocessable Entity` with a field-level error list describing what failed.

```python
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
```

The consequence worth internalising is that handlers should contain no input
validation. If a handler is checking whether a field is present or a number is
in range, that constraint belongs on the schema, where it is enforced uniformly
and shows up in the generated docs.

## Status codes

The default `200` is frequently a lie. Set the code explicitly:

- `201 Created` — a resource now exists; return it or its location.
- `202 Accepted` — the work was queued, not done. The correct code for any
  endpoint that hands off to a worker.
- `204 No Content` — success with nothing to return; the body must be empty.
- `409 Conflict` — the request is valid but the current state forbids it, such
  as registering an email that already exists.
- `422` — validation failed (FastAPI's default for a bad body).

`202` matters for asynchronous pipelines: it tells the client the response does
not mean the work finished, which is the difference between a client that polls
and one that assumes.

## Routers and prefixes

`APIRouter` composes. A route file declares paths relative to its own prefix,
and the application assembles them:

```python
router = APIRouter(prefix="/sessions", tags=["sessions"])
app.include_router(api_router, prefix="/api/v1")
```

The full path is the concatenation, so a version bump changes one string rather
than every decorator.

Dependencies declared at router level apply to every route in the file,
including ones added later:

```python
router = APIRouter(
    prefix="/recruiter",
    dependencies=[Depends(require_role(UserRole.recruiter))],
)
```

That is security by construction: a new endpoint in that file is role-gated
because of where it lives, not because its author remembered.

## Dependencies that take parameters

`require_role(UserRole.recruiter)` is not a dependency — it is a function that
*builds* one:

```python
def require_role(*roles: UserRole):
    async def guard(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(403, "Insufficient role")
        return user
    return guard
```

That is why it is written with call parentheses inside `Depends(...)` while
`Depends(get_db)` is not. The factory pattern is how a dependency gets
configured per use site.

## Background tasks versus a task queue

`BackgroundTasks` runs a callable in the same process, after the response is
sent. It is genuinely simple — no broker, no worker — and genuinely fragile:
the work is held in memory, so a restart, a crash or a deploy loses it silently,
and it competes for the same event loop as incoming requests.

Use it for best-effort side effects where loss is acceptable: a notification
email, a cache warm.

Anything that must survive, must retry, or takes real time belongs on a queue
such as Celery or RQ. The job is durable in a broker, a worker can retry it with
backoff, and workers scale independently of the API. The cost is operational —
a broker to run and a second process to deploy.

## Middleware

Middleware wraps every request and response, outside the routing and dependency
machinery:

```python
app.add_middleware(CORSMiddleware, allow_origins=[...], allow_credentials=True)
```

It is for cross-cutting concerns that apply uniformly — CORS, request logging,
compression, a correlation ID header. It is **not** where business logic goes:
middleware has no access to the resolved dependency tree, cannot use `Depends`,
and runs for every path including ones it knows nothing about. Logic that needs
the current user or the database session belongs in a dependency.

## The application factory

Constructing the app inside a function rather than at module scope lets it be
built more than once with different settings, which is what test fixtures want:

```python
def create_app() -> FastAPI:
    app = FastAPI(title=settings.PROJECT_NAME)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app

app = create_app()
```

`uvicorn app.main:app` imports the module and takes the module-level instance.
`app.dependency_overrides[get_db] = ...` is how a test swaps a real dependency
for a fake without touching application code.
