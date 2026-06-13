/** @type {import('next').NextConfig} */
const nextConfig = {
  // FastAPI runs at this URL inside docker (api:8000) or localhost:8088 in dev.
  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL || "http://localhost:8088",
  },
  // Make `next start` and `next build` happy in a slim Docker image.
  output: "standalone",
  experimental: {
    optimizePackageImports: ["lucide-react"],
  },
};

export default nextConfig;
