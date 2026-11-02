import type { NextConfig } from "next";

// HTTP goes through this app (queries, mutations, the triage SSE stream), proxied to the API, so there's no CORS.
// GraphQL subscriptions open a WebSocket straight to the API (NEXT_PUBLIC_GRAPHQL_WS): Next's rewrites don't
// proxy WebSocket upgrades. The API allows this origin for them (settings.web_origins).
const API_URL = process.env.API_URL ?? "http://localhost:8001";

const config: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      { source: "/graphql", destination: `${API_URL}/graphql` },
      { source: "/v1/:path*", destination: `${API_URL}/v1/:path*` },
    ];
  },
};

export default config;
