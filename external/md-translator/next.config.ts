import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
const withNextIntl = createNextIntlPlugin();

// Docker/local service mode: standalone output with API routes
// Static deployment: export mode
const isServerMode = process.env.DOCKER_BUILD === "true" || process.env.LOCAL_API_SERVER === "true";

const nextConfig: NextConfig = {
  output: isServerMode ? "standalone" : "export",
  images: {
    unoptimized: true,
  },
  reactCompiler: true,
  experimental: {
    optimizePackageImports: ["antd", "@ant-design/icons"],
  },
};

export default withNextIntl(nextConfig);
