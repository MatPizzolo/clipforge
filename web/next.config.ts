import type { NextConfig } from "next";
import { assertAuthBypassAllowed } from "./lib/authMode";
import { assertMockAllowed } from "./lib/mockGuard";

// Fails `next build` when MOCK_API is set on Vercel production, or AUTH_DISABLED on any Vercel
// environment (it's for local testing only).
assertMockAllowed(process.env);
assertAuthBypassAllowed(process.env);

const nextConfig: NextConfig = {
  poweredByHeader: false,
};

export default nextConfig;
