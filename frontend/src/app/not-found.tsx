import Link from "next/link";
import { Compass } from "lucide-react";
import { buttonClass, Card, Shell } from "@/components/ui";

/** Any URL that matches no page. */
export default function NotFound() {
  return (
    <Shell width="narrow" className="sm:pt-24">
      <Card className="flex flex-col items-start gap-4 p-8">
        <span className="flex size-12 items-center justify-center rounded-2xl bg-accent-subtle text-accent">
          <Compass aria-hidden="true" className="size-6" />
        </span>
        <span className="tabular font-display text-sm font-bold tracking-[0.08em] text-accent">
          404
        </span>
        <h1 className="font-display text-[28px] font-bold tracking-[-0.02em]">Page not found</h1>
        <p className="text-ink-2">
          There&apos;s nothing at this address. If you followed a link to an interview or a
          report, it may belong to a different account.
        </p>
        <Link href="/" className={buttonClass("primary")}>
          Go to the home page
        </Link>
      </Card>
    </Shell>
  );
}
