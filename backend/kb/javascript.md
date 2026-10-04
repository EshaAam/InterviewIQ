---
title: JavaScript
topic: javascript
license: hand-written for InterviewIQ
url:
---

# JavaScript

## The event loop

JavaScript runs on a single thread with one call stack. Asynchronous work is
handed to the host — the browser or Node — which does it elsewhere and puts a
callback on a queue when it finishes. The event loop takes the next callback off
the queue only when the stack is empty.

That is why a long synchronous loop freezes a page: nothing else can run until
the stack unwinds.

There are two queues, and the ordering between them is the detail that matters.
**Microtasks** — promise callbacks, `queueMicrotask`, `await` continuations —
drain *completely* after the current task and before the next macrotask.
**Macrotasks** are timers, I/O callbacks, UI events.

```js
console.log("A");
setTimeout(() => console.log("B"), 0);
Promise.resolve().then(() => console.log("C"));
console.log("D");
// A D C B
```

`C` precedes `B` despite the zero-millisecond timer, because the microtask queue
drains first. A microtask that schedules another microtask can therefore starve
timers indefinitely.

## Closures

A function keeps access to the scope it was *defined* in, and those variables
survive after the outer call returns:

```js
function counter() {
  let count = 0;
  return () => ++count;
}
const next = counter();
next();  // 1
next();  // 2
```

`count` is unreachable from outside, which is how closures provide private
state. The same mechanism powers factory functions, partial application, and
the module pattern.

Capture is **by reference, not by value** — the classic `var` loop bug:

```js
for (var i = 0; i < 3; i++) setTimeout(() => console.log(i));  // 3 3 3
for (let i = 0; i < 3; i++) setTimeout(() => console.log(i));  // 0 1 2
```

`var` has one binding for the whole loop; `let` creates a fresh binding per
iteration.

## var, let and const

`var` is function-scoped and hoisted: the declaration moves to the top of the
function and the variable is `undefined` until the assignment runs.

`let` and `const` are block-scoped. They are hoisted too, but into a **temporal
dead zone** — referencing one before its declaration throws a `ReferenceError`
rather than quietly giving `undefined`. That is the better failure.

`const` prevents **rebinding**, not mutation:

```js
const config = { retries: 3 };
config.retries = 5;      // fine - the object is mutable
config = {};             // TypeError - the binding is not
```

Use `const` by default and `let` when a variable genuinely changes. `var` has no
remaining use in new code.

## Promises

A promise is an object representing a value that is not ready yet. It replaced
callbacks for three reasons:

**Flat composition.** `.then` chains instead of nesting, so sequential async
steps read top to bottom rather than drifting rightwards.

**Error propagation.** A rejection skips the remaining `.then` handlers and
lands in the nearest `.catch`, so one handler covers a whole chain. With
callbacks every level had to check and forward an error itself.

**Combinators.** `Promise.all` (all succeed, or reject on the first failure),
`Promise.allSettled` (wait for all outcomes), `Promise.race`, `Promise.any`.
Expressing "do these three concurrently and wait for all" with raw callbacks
means writing a counter by hand.

`async`/`await` is syntax over the same objects: an `async` function returns a
promise, and `await` suspends until one settles. `try/catch` then works on async
code the way it does on synchronous code.

## Prototypal inheritance

Every object has a hidden link to another object, its prototype. A property
lookup that misses walks up that chain until it finds the property or reaches
`null`.

```js
const base = { greet() { return "hi"; } };
const derived = Object.create(base);
derived.greet();     // found on base via the chain
```

This is *delegation*, not copying: changing `base.greet` changes behaviour for
everything delegating to it, immediately.

`class` syntax is sugar over exactly this mechanism — methods go on
`Constructor.prototype`, and `extends` links one prototype to another. There is
no separate classical inheritance system underneath; the sugar just makes the
common arrangement readable.

## == versus ===

`===` compares without conversion: different types means not equal.

`==` applies the abstract equality algorithm, which coerces operands before
comparing. The results are famously inconsistent:

```js
0 == "";          // true
0 == "0";         // true
"" == "0";        // false   - so == is not transitive
null == undefined // true
null == 0;        // false
NaN == NaN;       // false
```

Use `===`. The one defensible exception is `x == null`, which tests for `null`
or `undefined` together.

For the edge cases `===` gets wrong — `NaN`, and `+0` versus `-0` —
`Object.is` is the precise comparison.

## this

`this` is determined by **how a function is called**, not where it was defined.
Four rules, in precedence order:

1. `new Fn()` — `this` is the new object.
2. `fn.call(obj)`, `fn.apply(obj)`, `fn.bind(obj)` — `this` is the given object.
3. `obj.fn()` — `this` is `obj`.
4. A plain `fn()` — `this` is `undefined` in strict mode, the global object
   otherwise.

This is why extracting a method loses its receiver:

```js
const { greet } = user;
greet();            // `this` is no longer `user`
```

Arrow functions are the exception: they have no `this` of their own and close
over the enclosing scope's lexically. That makes them right for callbacks inside
a method and wrong as methods themselves, since an arrow method never gets the
instance.

## Debounce and throttle

Both limit how often a handler runs; they differ in *when*.

**Debounce** waits for a quiet period and then fires once. Keystrokes in a
search box collapse into a single request after typing stops.

**Throttle** fires at most once per interval regardless of how many events
arrive. A scroll or resize handler runs at a steady rate instead of on every
pixel.

```js
function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
```

Implementations usually offer leading and trailing variants: fire immediately
then suppress, or suppress then fire at the end. The default above is trailing.
Choosing wrong makes a UI feel laggy — a leading-edge debounce on a search box
fires on the first keystroke, which is exactly the request you did not want.

## Shallow equality and React rendering

React decides whether to re-render by comparing props and state with
`Object.is`, a reference comparison for objects. An object or array literal
created during render is a new reference every time, so a memoised child
re-renders regardless:

```jsx
<Child options={{ sort: "asc" }} />   // new object each render
```

`useMemo` and `useCallback` exist to stabilise those references. The same rule
explains why state updates must be immutable: mutating an array in place leaves
the reference unchanged, React sees no difference, and the UI does not update.

## Event delegation

Events bubble from the target up through its ancestors, so one listener on a
container can serve many children:

```js
list.addEventListener("click", (event) => {
  const item = event.target.closest("li");
  if (item) select(item.dataset.id);
});
```

One listener instead of hundreds, and it keeps working for rows added later —
which a per-element listener does not, because it was never attached to them.
This is the mechanism React's synthetic event system generalises.
