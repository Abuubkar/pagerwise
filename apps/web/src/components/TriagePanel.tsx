"use client";

import { useEffect, useState } from "react";
import { TriageBrief } from "@/components/TriageBrief";
import { applyEvent, emptyBrief, streamTriage } from "@/lib/triage";

// Opens the incident's triage stream and shows the brief as it arrives: live while the worker writes it, replayed
// once it's done. `version` re-opens the stream when a newer triage starts.
export function TriagePanel({ incidentId, triageId, baseUrl = "" }: { incidentId: string; triageId: string | null; baseUrl?: string }) {
  const [state, setState] = useState(emptyBrief);
  const [status, setStatus] = useState<"loading" | "streaming" | "none" | "failed">("loading");

  useEffect(() => {
    const abort = new AbortController();
    setState(emptyBrief());
    setStatus("streaming");
    streamTriage(incidentId, (event, data) => setState(s => applyEvent(s, event, data)), abort.signal, baseUrl)
      .then(result => result === "none" && setStatus("none"))
      .catch(() => !abort.signal.aborted && setStatus("failed"));
    return () => abort.abort();
  }, [incidentId, triageId, baseUrl]);

  if (status === "none") return <p className="muted">No triage yet.</p>;
  if (status === "failed") return <p role="alert" className="banner bad">Couldn&apos;t load the triage stream.</p>;
  const writing = !state.brief && !state.error;
  return (
    <div>
      {writing && <p className="muted">{state.text ? "Writing the brief…" : "Waiting for the triage worker…"}</p>}
      <TriageBrief state={state} />
    </div>
  );
}
