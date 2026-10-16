import { Landing } from "@/components/landing/landing";

/**
 * The public front door. Anyone can read it; signing in is asked for only
 * when someone starts an interview (see `Landing`). A server component, so
 * the page itself is static and only the interactive parts ship as client JS.
 */
export default function Home() {
  return <Landing />;
}
