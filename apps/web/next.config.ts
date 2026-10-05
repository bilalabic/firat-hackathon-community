import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  poweredByHeader: false,
  cacheLife: {
    // Event data and phases (PUBLIC_WEB §2): refreshed in the background after 1 h, and never
    // served older than 2 h, so a phase ("Başvurular açık", "Son günler") is at most ~2 h late
    // even after a quiet period. On-demand revalidation via tags is the normal path.
    events: { stale: 300, revalidate: 3600, expire: 7200 },
  },
  images: {
    // Organizer posters are external. Hosts are added here explicitly when needed
    // (PUBLIC_WEB §5); until then posters use a plain <img>.
    remotePatterns: [],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
