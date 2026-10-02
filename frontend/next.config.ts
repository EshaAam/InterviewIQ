import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The production image runs `.next/standalone/server.js`: only the files the
  // server actually needs are copied there, so the image carries no full
  // node_modules. `next dev` and `next start` are unaffected.
  output: "standalone",
  // `/recruiter` has no page of its own; send it to the recruiter home.
  // Temporary (307) so browsers don't cache it if an index page is added later.
  async redirects() {
    return [
      { source: "/recruiter", destination: "/recruiter/review", permanent: false },
    ];
  },
};

export default nextConfig;
