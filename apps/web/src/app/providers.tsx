"use client";

import { type ReactNode, useState } from "react";
import { Provider } from "urql";
import { makeClient } from "@/lib/client";

const WS_URL = process.env.NEXT_PUBLIC_GRAPHQL_WS ?? "ws://localhost:8001/graphql";

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(() => makeClient("/graphql", WS_URL));
  return <Provider value={client}>{children}</Provider>;
}
