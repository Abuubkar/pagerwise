"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery, useSubscription } from "urql";
import type { IncidentsQuery as IncidentsResult } from "@/gql/graphql";
import { appendPage, upsertTop } from "@/lib/incidents";
import { IncidentUpdatedSubscription, IncidentsQuery } from "@/lib/queries";

type Row = IncidentsResult["incidents"]["edges"][number]["node"];
const PAGE = 20;

export function IncidentList({ pageSize = PAGE }: { pageSize?: number }) {
  const [after, setAfter] = useState<string | null>(null);
  const [rows, setRows] = useState<Row[]>([]);
  // Live updates seen so far, newest first. A first page that arrives after some of them must not hide them.
  const live = useRef<Row[]>([]);
  const [{ data, fetching, error }] = useQuery({ query: IncidentsQuery, variables: { first: pageSize, after } });

  useEffect(() => {
    if (!data) return;
    const page = data.incidents.edges.map(edge => edge.node);
    if (after !== null) setRows(current => appendPage(current, page));
    else setRows([...live.current].reverse().reduce((list, row) => upsertTop(list, row), page));
  }, [data, after]);

  // New and changed incidents arrive live and go to the top.
  useSubscription({ query: IncidentUpdatedSubscription }, (_, event) => {
    live.current = upsertTop(live.current, event.incidentUpdated);
    setRows(current => upsertTop(current, event.incidentUpdated));
    return event;
  });

  if (error) return <p role="alert" className="banner bad">Couldn&apos;t load incidents: {error.message}</p>;
  return (
    <div>
      <table className="incidents">
        <thead><tr><th>Severity</th><th>Incident</th><th>Service</th><th>Alerts</th><th>Status</th><th>Opened</th></tr></thead>
        <tbody>
          {rows.map(incident => (
            <tr key={incident.id} data-testid="incident-row">
              <td><span className={`badge ${incident.severity}`}>{incident.severity}</span></td>
              <td><Link href={`/incidents/${incident.id}`}>{incident.title}</Link></td>
              <td>{incident.service}</td>
              <td className="num">{incident.alertCount.toLocaleString("en-US")}</td>
              <td>{incident.status}</td>
              <td><time dateTime={incident.openedAt}>{new Date(incident.openedAt).toLocaleString("en-GB", { timeZone: "UTC" })}</time></td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && !fetching && <p className="muted">No incidents yet.</p>}
      {data?.incidents.pageInfo.hasNextPage && (
        <button disabled={fetching} onClick={() => setAfter(data.incidents.pageInfo.endCursor ?? null)}>
          {fetching ? "Loading…" : "Load more"}
        </button>
      )}
    </div>
  );
}
