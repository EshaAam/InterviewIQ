---
title: Python
topic: python
license: hand-written for InterviewIQ
url:
---

# Python

## The GIL

CPython protects its interpreter state with a single mutex, the Global
Interpreter Lock. Only one thread executes Python bytecode at a time, no matter
how many cores the machine has.

The practical consequence is that threads do not speed up CPU-bound Python. Two
threads summing a large list take as long as one, plus the cost of switching
between them. For CPU-bound work the options are `multiprocessing` (separate
interpreters, separate GILs, at the cost of pickling data between them) or
pushing the hot loop into a C extension.

The lock is released around blocking I/O — a socket read, a disk write, a
`time.sleep` — and inside C extensions that choose to drop it, which numpy does
for large array operations. That is why threaded I/O still scales well: the
threads spend their time waiting with the lock released, not holding it.

The GIL is an implementation detail of CPython, not of the language. Jython and
IronPython have no GIL, and ongoing work on a free-threaded CPython aims to
remove it.

## Generators and laziness

A function containing `yield` returns a generator: it produces values one at a
time and suspends between them, keeping its local state alive.

The practical difference from returning a list is memory. Building a list of a
million rows holds a million rows. Yielding them holds one. Reading a 10 GB log
file line by line is possible; loading it into a list is not.

Generators can also represent sequences with no end, because nothing is
materialised until it is asked for:

```python
def counter(start=0):
    while True:
        yield start
        start += 1
```

The trade-off is that a generator is consumed once and has no length. If the
caller needs to iterate twice, index into the result, or ask how many items
there are, a list is the right answer.

## Identity versus equality

`is` compares identity — whether two names refer to the same object in memory.
`==` compares value, which for most types means calling `__eq__`.

Use `is` only for singletons: `None`, `True`, `False`. `x is None` is correct;
`x == None` works but invites a custom `__eq__` to lie about it.

The trap is interning. CPython reuses small integers (-5 to 256) and some short
strings, so `a is b` can be `True` for two separately-written literals:

```python
a, b = 256, 256
a is b          # True  - interned
a, b = 257, 257
a is b          # False - separate objects, usually
```

Code that works for small values and breaks for large ones is the symptom of
using `is` where `==` was meant. The interning rules are an optimisation, not a
guarantee, and they differ between interpreters and even between the REPL and a
script.

## Decorators

A decorator is a callable that takes a function and returns a function. `@name`
above a `def` is syntactic sugar applied once, at definition time:

```python
def log_calls(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        print(f"calling {func.__name__}")
        return func(*args, **kwargs)
    return wrapper
```

`functools.wraps` copies `__name__`, `__doc__` and `__wrapped__` onto the
wrapper. Without it the decorated function reports itself as `wrapper`, which
breaks introspection, documentation tools and anything that dispatches on a
function's name.

Decorators that take arguments need a third layer: a function that returns a
decorator that returns a wrapper. That extra level is why `@retry(times=3)` has
call parentheses and `@log_calls` does not.

## Context managers

A context manager guarantees that cleanup runs, including when the block raises.
`__enter__` runs on entry, `__exit__` runs on exit no matter how the block is
left:

```python
with open(path) as handle:
    process(handle)      # handle is closed even if this raises
```

That is a stronger guarantee than relying on garbage collection. CPython's
reference counting usually closes a dropped file promptly, but that is an
implementation detail, and on an interpreter with a different collector the file
may stay open indefinitely. The `with` block makes the release point explicit
and deterministic.

`contextlib.contextmanager` turns a generator into one: everything before the
`yield` is setup, everything after is teardown, and a `try/finally` around the
`yield` ensures teardown survives an exception in the body.

## Mutable default arguments

Default arguments are evaluated **once**, when the `def` executes — not on each
call. A mutable default is therefore shared by every call:

```python
def append_to(item, target=[]):     # wrong
    target.append(item)
    return target

append_to(1)    # [1]
append_to(2)    # [1, 2]  - the same list
```

The fix is a sentinel:

```python
def append_to(item, target=None):
    if target is None:
        target = []
    target.append(item)
    return target
```

The same evaluation rule makes `def f(now=datetime.now())` freeze the timestamp
at import. Anything mutable or time-dependent belongs inside the body.

## Shallow and deep copies

`copy.copy` duplicates the outer container and leaves the references inside it
pointing at the same objects. `copy.deepcopy` recurses, duplicating the whole
graph.

```python
rows = [[1, 2], [3, 4]]
shallow = copy.copy(rows)
shallow[0].append(99)
rows[0]                  # [1, 2, 99] - the inner lists are shared
```

`deepcopy` also tracks objects it has already copied, so a structure containing
a cycle terminates instead of recursing forever. It is correspondingly slow, and
it will happily copy things you did not mean to — a deepcopy of an object
holding a database connection is rarely what anyone wanted.

## async and await

`async`/`await` is cooperative concurrency on a **single thread**. An `await`
marks a point where the coroutine may suspend and the event loop may run
something else. Nothing runs in parallel; the loop interleaves tasks at those
suspension points.

This is a win for I/O-bound work. A thousand concurrent HTTP requests spend
almost all their time waiting, and one thread can hold a thousand suspended
coroutines cheaply.

It does nothing for CPU-bound work. A tight numeric loop inside a coroutine
never awaits, so it blocks the loop and every other task behind it. The common
production bug is a blocking call — a synchronous database driver, `requests`,
`time.sleep` — inside an `async def`: it stalls the entire process, and the
symptom is unrelated endpoints getting slow.

`asyncio.to_thread` is the escape hatch, moving a blocking call onto a thread so
the loop stays free.

## Exceptions and the EAFP style

Python prefers "easier to ask forgiveness than permission": attempt the
operation and handle the failure, rather than checking first.

```python
try:
    value = mapping[key]
except KeyError:
    value = default
```

Checking first — "look before you leap" — introduces a race in concurrent code:
the key can disappear between the check and the access. It is also slower in the
common case, because the check runs every time while the exception costs only
when it fires.

Catch the narrowest exception that covers the case. A bare `except:` swallows
`KeyboardInterrupt` and `SystemExit` as well as the error you meant to handle,
which turns a Ctrl-C into a confusing no-op.

## Type hints

Annotations are not enforced at runtime; nothing checks them unless a tool does.
Their value is in that tooling — a type checker catching a wrong argument before
it ships, and an editor offering accurate completions.

`from __future__ import annotations` defers evaluation, so annotations become
strings and a class can reference itself or a type imported only for checking.
That is what makes `if TYPE_CHECKING:` imports work without a runtime cost.

Pydantic is the notable exception: it reads annotations at runtime and validates
against them, which is how FastAPI turns a function signature into a request
parser.
