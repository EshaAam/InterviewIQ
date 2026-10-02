"use client"; // error boundaries must be client components

import "./globals.css";

/**
 * The last line of defence: an error in the root layout itself, where
 * `error.tsx` can't help (it renders *inside* that layout). It replaces the
 * whole document, so it brings its own <html>, <body> and stylesheet, and
 * leans on nothing that might be what broke.
 */
export default function GlobalError({ retry }: { error: Error; retry: () => void }) {
  return (
    <html lang="en">
      <body className="flex min-h-full flex-col items-center justify-center gap-3 p-6 text-center">
        <title>Something went wrong · InterviewIQ</title>
        <h1 className="text-xl font-semibold">Something went wrong</h1>
        <p className="text-sm">The app failed to load. Your saved work is safe on the server.</p>
        <button
          onClick={() => retry()}
          className="btn-brand cursor-pointer rounded-control px-6 py-3 text-[15px] font-semibold"
        >
          Try again
        </button>
      </body>
    </html>
  );
}
