---
title: TypeScript
topic: typescript
license: hand-written for InterviewIQ
url:
---

# TypeScript

## What does TypeScript add over JavaScript, and what does it not do?

TypeScript adds static types that are checked at compile time. Mistakes like
calling a method that does not exist, passing a string where a number is
expected, or forgetting that a value can be `undefined` are caught in the editor
instead of in production. Types also make large codebases easier to refactor and
document intent.

What it does not do is check anything at runtime. Types are erased during
compilation, so the output is plain JavaScript. Data that crosses a boundary —
an API response, a form submission, JSON from local storage — is not guaranteed
to match its declared type. A cast such as `as User` only tells the compiler to
trust you. Untrusted data has to be validated at runtime, for example with a
schema library like Zod, which can also generate the TypeScript type.

## What is the difference between an interface and a type alias?

Both can describe the shape of an object, and for most object types either
works. An `interface` can be extended with `extends` and can be declared more
than once, with the declarations merged — useful for augmenting library types.
A `type` alias cannot be reopened, but it can name things an interface cannot:
unions (`"admin" | "user"`), tuples, mapped types and conditional types.

A common convention is to use interfaces for object shapes that other code may
extend, and type aliases for unions and computed types. Consistency within a
codebase matters more than which one is chosen.

## What are generics and when do you need them?

Generics let a function or type work with many types while keeping the
relationship between them. `function first<T>(items: T[]): T | undefined`
returns the same type the array holds; without the generic it would have to
return `any` and lose all type information.

They are needed whenever the output type depends on the input type: a typed API
client `fetchJson<T>(url): Promise<T>`, a cache, a `useState<T>` hook, a
repository for many entities. Constraints narrow what a generic accepts, for
example `<T extends { id: string }>` for a function that must read an id.

## What is the difference between any, unknown and never?

`any` turns type checking off for that value: anything can be done with it and
errors spread silently. `unknown` is the safe version — it can hold anything,
but you must narrow it (with `typeof`, `instanceof` or a validation function)
before using it. Parsed JSON and caught errors are good candidates for `unknown`.

`never` is the type with no values. It is the return type of a function that
always throws, and it appears when every possibility has been ruled out. That
makes it useful for exhaustiveness checks: in a `switch` over a union, assigning
the value to a `never` variable in the default branch makes the compiler fail
when a new case is added but not handled.

## How do union types and narrowing work?

A union type says a value can be one of several types: `string | null`, or
`"pending" | "paid" | "shipped"`. Before using it, code narrows it with a check
the compiler understands — `typeof x === "string"`, `x !== null`, `"error" in result`.

A discriminated union is the most useful pattern: every member has a common
literal field, such as `{ status: "ok"; data: User } | { status: "error"; message: string }`.
Checking `result.status` tells the compiler exactly which shape you have, so
accessing `data` in the error branch is a compile error. This models API results
and state machines much more safely than optional fields that may or may not be
set together.

## Which utility types do you use most?

`Partial<T>` makes every field optional, which suits an update payload.
`Pick<T, "id" | "name">` and `Omit<T, "password">` derive smaller types from a
larger one, so a public user type cannot accidentally include the password hash.
`Record<K, V>` types a dictionary; with a union as the key it forces every case
to be present. `ReturnType<typeof fn>` and `Awaited<T>` derive types from
existing functions instead of repeating them.

Deriving types this way keeps a single source of truth: change the base type
and every derived type follows.

## Why turn on strict mode?

`"strict": true` enables a group of checks, the most important being
`strictNullChecks`. Without it, `null` and `undefined` are allowed everywhere and
the most common runtime error in JavaScript — reading a property of undefined —
goes unchecked. With it, a value that may be missing has to be handled before use.

It also enables `noImplicitAny`, which stops untyped parameters from silently
becoming `any`. Turning strict mode on in an existing project produces many
errors at once; doing it file by file, or from the start of a new project, is
far less painful.
