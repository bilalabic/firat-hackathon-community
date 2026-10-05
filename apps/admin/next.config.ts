import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    serverActions: {
      // Same-origin only (the default, stated explicitly). Host names themselves are
      // checked against ADMIN_ALLOWED_HOSTS in src/proxy.ts.
      allowedOrigins: [],
    },
  },
};

export default nextConfig;
