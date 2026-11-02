import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { HttpResponse } from "msw/http";
import { IncidentList } from "@/components/IncidentList";
import { Providers, gql, server, socket } from "@/testing";

const incident = (n: number, extra: Record<string, unknown> = {}) => ({
  __typename: "Incident", id: `inc-${n}`, title: `Incident ${n}`, service: "ledger", severity: "sev1", status: "open",
  openedAt: `2026-11-02T12:0${n}:00Z`, lastAlertAt: `2026-11-02T12:0${n}:30Z`, alertCount: 10 * n, version: 1, ...extra,
});
const page = (nodes: ReturnType<typeof incident>[], endCursor: string | null, hasNextPage: boolean) => ({
  incidents: { __typename: "IncidentConnection", edges: nodes.map(node => ({ __typename: "IncidentEdge", cursor: `c-${node.id}`, node })),
               pageInfo: { __typename: "PageInfo", hasNextPage, endCursor } },
});
const titles = () => screen.getAllByTestId("incident-row").map(row => row.querySelector("a")!.textContent);

test("the list pages with cursors", async () => {
  const asked: (string | null)[] = [];
  server.use(gql.query("Incidents", ({ variables }) => {
    asked.push(variables.after);
    return HttpResponse.json({ data: variables.after === null
      ? page([incident(3), incident(2)], "c-inc-2", true)
      : page([incident(1)], "c-inc-1", false) });
  }));
  render(<IncidentList pageSize={2} />, { wrapper: Providers });

  await waitFor(() => expect(titles()).toEqual(["Incident 3", "Incident 2"]));
  fireEvent.click(screen.getByRole("button", { name: "Load more" }));
  await waitFor(() => expect(titles()).toEqual(["Incident 3", "Incident 2", "Incident 1"]));
  expect(asked).toEqual([null, "c-inc-2"]); // the second page asked for what came after the first page's last row
  expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
});

test("a subscription update moves the incident to the top", async () => {
  server.use(gql.query("Incidents", () => HttpResponse.json({ data: page([incident(3), incident(2), incident(1)], null, false) })));
  // The API's side of graphql-transport-ws: acknowledge the connection, then push one update for the subscription.
  server.use(socket.addEventListener("connection", ({ client }) => {
    client.addEventListener("message", event => {
      const message = JSON.parse(String(event.data));
      if (message.type === "connection_init") client.send(JSON.stringify({ type: "connection_ack" }));
      if (message.type === "subscribe") {
        expect(message.payload.query).toContain("incidentUpdated");
        client.send(JSON.stringify({ id: message.id, type: "next", payload: { data: {
          incidentUpdated: incident(1, { alertCount: 999, version: 2, severity: "sev1" }) } } }));
      }
    });
  }));
  render(<IncidentList />, { wrapper: Providers });

  await waitFor(() => expect(titles()).toEqual(["Incident 1", "Incident 3", "Incident 2"]));
  expect(screen.getAllByTestId("incident-row")[0]).toHaveTextContent("999"); // the updated row, not a duplicate
  expect(screen.getAllByTestId("incident-row")).toHaveLength(3);
});
