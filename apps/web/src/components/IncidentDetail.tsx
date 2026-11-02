"use client";

import { useState } from "react";
import { useMutation, useQuery } from "urql";
import { TriagePanel } from "@/components/TriagePanel";
import { AcknowledgeMutation, IncidentQuery } from "@/lib/queries";

const time = (iso: string) => new Date(iso).toLocaleTimeString("en-GB", { timeZone: "UTC" });

export function IncidentDetail({ id }: { id: string }) {
  const [{ data, error }, refetch] = useQuery({ query: IncidentQuery, variables: { id }, requestPolicy: "cache-and-network" });
  const [ack, acknowledge] = useMutation(AcknowledgeMutation);
  const [conflict, setConflict] = useState<string | null>(null);

  if (error) return <p role="alert" className="banner bad">{error.message}</p>;
  const incident = data?.incident;
  if (!incident) return <p className="muted">Loading…</p>;

  async function onAcknowledge() {
    setConflict(null);
    const result = await acknowledge({ id, expectedVersion: incident!.version });
    const outcome = result.data?.acknowledgeIncident;
    if (outcome?.__typename === "VersionConflict") {
      setConflict(`The incident changed (version ${outcome.expectedVersion} → ${outcome.currentVersion}) since you ` +
        "opened it: a new kind of alert joined or severity rose. Review it again before acknowledging.");
    }
    refetch({ requestPolicy: "network-only" });
  }

  // The timeline: when it opened, each alert group's span, and the triage.
  const entries = [
    { at: incident.openedAt, text: `Opened by ${incident.title}` },
    ...incident.alerts.map(a => ({
      at: a.firstAt, text: `${a.alertname ?? a.fingerprint} on ${a.instance ?? a.service}: ` +
        `${a.count.toLocaleString("en-US")} alerts until ${time(a.lastAt)}`,
    })),
    ...(incident.triage ? [{ at: incident.triage.createdAt, text: `Triage queued (version ${incident.triage.incidentVersion})` }] : []),
    ...(incident.triage?.finishedAt ? [{ at: incident.triage.finishedAt, text: `Triage ${incident.triage.status}${incident.triage.verdict ? `: ${incident.triage.verdict}` : ""}` }] : []),
  ].sort((a, b) => a.at.localeCompare(b.at));

  return (
    <div className="detail">
      <header>
        <span className={`badge ${incident.severity}`}>{incident.severity}</span>
        <h2>{incident.title}</h2>
        <p className="muted">{incident.service} · {incident.status} · version {incident.version} ·{" "}
          {incident.alertCount.toLocaleString("en-US")} alerts</p>
        {incident.status === "open" && (
          <button onClick={onAcknowledge} disabled={ack.fetching}>Acknowledge</button>
        )}
        {conflict && <p role="alert" className="banner warn">{conflict}</p>}
      </header>
      <div className="columns">
        <section aria-label="Timeline">
          <h3>Timeline (UTC)</h3>
          <ol className="timeline">
            {entries.map((e, i) => <li key={i}><time dateTime={e.at}>{time(e.at)}</time> {e.text}</li>)}
          </ol>
        </section>
        <section aria-label="Triage brief">
          <h3>Triage brief</h3>
          <TriagePanel incidentId={id} triageId={incident.triage?.id ?? null} />
        </section>
      </div>
    </div>
  );
}
