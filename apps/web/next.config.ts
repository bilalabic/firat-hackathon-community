import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  images: {
    // Organizer posters are external. Hosts are added here explicitly when needed
    // (PUBLIC_WEB §5); until then posters use a plain <img>.
    remotePatterns: [],
  },
};

export default nextConfig;
