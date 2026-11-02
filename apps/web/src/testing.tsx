// Shared test setup: the real urql client (HTTP and graphql-ws) against MSW handlers.
import type { ReactNode } from "react";
import { Provider } from "urql";
import { graphql } from "msw/graphql";
import { setupServer } from "msw/node";
import { ws } from "msw/ws";
import { makeClient } from "@/lib/client";

export const API = "http://localhost";
export const GRAPHQL_URL = `${API}/graphql`;
export const WS_URL = "ws://localhost/graphql";
// MSW 3 scopes GraphQL and WebSocket handlers to an endpoint.
export const gql = graphql.link(GRAPHQL_URL);
export const socket = ws.link(WS_URL);
export const server = setupServer();
beforeAll(() => server.listen({ onUnhandledFrame: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

export function Providers({ children }: { children: ReactNode }) {
  // Node's fetch needs absolute URLs; the app itself uses "/graphql" through the Next.js proxy.
  return <Provider value={makeClient(GRAPHQL_URL, WS_URL)}>{children}</Provider>;
}

/** A text/event-stream response that sends these events, in order, as the API would. */
export function sseResponse(events: [string, unknown][]): Response {
  const body = events.map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  const bytes = new TextEncoder().encode(body);
  const stream = new ReadableStream({
    start(controller) { // in small pieces: an event can be split across network reads
      for (let i = 0; i < bytes.length; i += 7) controller.enqueue(bytes.slice(i, i + 7));
      controller.close();
    },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream" } });
}
