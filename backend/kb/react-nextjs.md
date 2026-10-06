---
title: React and Next.js
topic: react-nextjs
license: hand-written for InterviewIQ
url:
---

# React and Next.js

## What does React's reconciliation do, and why do list items need keys?

When state changes, React re-renders components into a new element tree and
compares it with the previous one, then applies only the differences to the
DOM. Touching the real DOM is the expensive part, so the comparison exists to
keep those writes minimal.

Keys tell React which item in a list is which between renders. With a stable key
(a database id), React can see that an item moved and keep its DOM node and its
state. Using the array index as a key breaks this when items are inserted,
removed or reordered: React matches by position, so state such as a half-typed
input or an expanded panel ends up attached to the wrong row. Keys must be
stable and unique among siblings, not globally.

## How do useState and useEffect work, and what goes wrong with effect dependencies?

`useState` stores a value across renders; calling its setter schedules a
re-render rather than changing the variable in place. `useEffect` runs after the
render is committed, for work that synchronises with something outside React —
a subscription, a timer, a network request.

The dependency array lists every value from the component that the effect
reads. Leave one out and the effect keeps using a stale value from an old
render. Include an object or function created during render and the effect
re-runs every time, because it is a new reference on each render. The cleanup
function runs before the next effect and on unmount, which is where you cancel
requests and clear timers. A common bug is an effect that sets state it depends
on, which loops forever.

## What is the difference between Server Components and Client Components?

In the Next.js App Router every component is a Server Component unless the file
starts with `"use client"`. Server Components run only on the server: they can
read the database or call internal services directly, and their code is never
sent to the browser, which keeps the bundle small.

They cannot use state, effects or browser APIs. Anything interactive — a form
with local state, an onClick handler, `window` — has to be a Client Component.
The directive marks a boundary: everything imported below it becomes client
code. A good pattern is to keep pages and data loading on the server and push
`"use client"` down to small interactive leaves, passing data in as props.
Props crossing the boundary must be serialisable, so you cannot pass a function
from a Server Component to a Client Component.

## How does caching and revalidation work in the Next.js App Router?

Next.js can cache the result of a server-side `fetch`, the rendered output of a
route, and data read through `unstable_cache`. The default behaviour has changed
between versions, so it is worth stating the policy explicitly rather than
relying on it.

Time-based revalidation (`revalidate: 60`) serves cached data and refreshes it
in the background once it is older than the window. On-demand revalidation is
usually better for data that changes on a user action: after an order is
created, a Server Action calls `revalidatePath("/admin/orders")` or
`revalidateTag("orders")`, and only the pages that depend on that data are
rebuilt. Tagging fetches by the data they use is what makes revalidation
granular — one product update invalidates that product, not the whole catalogue.

## What are Server Actions and when would you use them?

A Server Action is an async function marked `"use server"` that a form or a
Client Component can call as if it were local; Next.js turns the call into a
POST request behind the scenes. It is a convenient place for mutations: create
an order, update a profile, then revalidate the affected pages.

Because a Server Action is a public HTTP endpoint, it needs the same care as any
API route. Validate the input on the server, check that the user is
authenticated and allowed to do the action, and never trust a price or a role
sent from the client. They suit mutations that belong to one app; a separate
REST API is still the better choice when mobile apps or third parties need the
same operations.

## How does dynamic routing work in Next.js?

A folder named in square brackets becomes a route parameter: `app/products/[slug]/page.tsx`
serves `/products/anything`. `[...slug]` catches several segments, and
`[[...slug]]` also matches the bare path.

From Next.js 15, `params` and `searchParams` are passed to a page as Promises,
so a Server Component awaits them and a Client Component unwraps them with
React's `use()`. `generateStaticParams` lists the parameter values to build
ahead of time, which turns a dynamic route into static pages for known slugs.
`notFound()` from `next/navigation` renders the 404 page when the slug does not
match a record, which is better than rendering an empty page with a 200 status.

## When would you choose static generation, server rendering or client rendering?

Static generation builds the page once and serves it from a CDN: fastest, and
right for marketing pages, docs and product pages that change rarely, especially
combined with revalidation. Server rendering on each request suits pages that
depend on the current user or must always be fresh, such as a dashboard or a
cart. Client-side rendering suits highly interactive regions after the first
load, like filters that update as you type.

Most real pages mix them. A product page can be statically generated with
revalidation, with a small client component for the stock count and the add to
cart button. The question to ask for each part is how fresh the data must be and
whether it differs per user.

## How would you implement infinite scroll?

Put an empty sentinel element after the last item and watch it with an
`IntersectionObserver`; when it scrolls into view, fetch the next page. This is
cheaper and more reliable than listening to scroll events.

Use cursor-based pagination rather than offsets: ask for "20 items after id X".
With offsets, an item inserted while the user scrolls shifts everything and
produces duplicates or gaps. Guard against firing two requests for the same page
when the sentinel stays visible, stop when the server says there is no more
data, and remove duplicates by id in case of retries. For very long lists,
virtualise the rendering so only visible rows exist in the DOM.

## How do you keep a Next.js app fast?

Send less JavaScript: keep components on the server where possible and load
heavy client-only widgets with `next/dynamic`. Use `next/image`, which serves
correctly sized, lazily loaded, modern-format images and reserves space to
prevent layout shift. Use `next/font` so fonts are self-hosted and do not flash.

Fetch data in parallel with `Promise.all` instead of awaiting requests one after
another, and stream slow parts of a page with `Suspense` so the rest shows
immediately. Avoid unnecessary re-renders in client components by keeping state
close to where it is used. Measure with Lighthouse and the Core Web Vitals —
Largest Contentful Paint, Interaction to Next Paint, Cumulative Layout Shift —
rather than guessing.
