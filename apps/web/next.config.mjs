/** @type {import('next').NextConfig} */
const nextConfig = {
  // Server-side proxy: the browser hits /api/... on the Next.js host; the
  // Next server rewrites that to the FastAPI URL (api:8000 inside docker,
  // localhost:8088 in dev). The browser never needs to know the API host —
  // fixes CORS and makes the same bundle run anywhere.
  async rewrites() {
    const target = process.env.ARYX_API_URL_INTERNAL || "http://api:8000";
    return [{ source: "/api/:path*", destination: `${target}/:path*` }];
  },
  // Make `next start` and `next build` happy in a slim Docker image.
  output: "standalone",
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
