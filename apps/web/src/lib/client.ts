import { createClient as createWsClient } from "graphql-ws";
import { cacheExchange, createClient, type Exchange, fetchExchange, subscriptionExchange } from "urql";

// Queries and mutations over HTTP (through the Next.js proxy); subscriptions over a graphql-transport-ws WebSocket
// straight to the API, when a wsUrl is given (in the browser, and in tests that mock the socket).
export function makeClient(url = "/graphql", wsUrl?: string) {
  const exchanges: Exchange[] = [cacheExchange, fetchExchange];
  if (wsUrl) {
    const ws = createWsClient({ url: wsUrl, lazy: true, retryAttempts: Infinity });
    exchanges.push(subscriptionExchange({
      forwardSubscription(request) {
        const input = { ...request, query: request.query ?? "" };
        return { subscribe: sink => ({ unsubscribe: ws.subscribe(input, sink) }) };
      },
    }));
  }
  return createClient({ url, exchanges });
}
