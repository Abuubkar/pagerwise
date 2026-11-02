import type { Citation, DegradedSource, ErrorEvent, TriageBrief } from "@/lib/api";
import { makeApi } from "@/lib/api";

// The triage brief as it streams: the SSE events of GET /v1/incidents/{id}/triage/stream folded into what the page
// shows. Event names and payloads are the contract's (contracts/openapi.yaml).
export type BriefState = {
  text: string; // the brief's markdown so far: the concatenated token events
  citations: Record<string, Citation>; // by tag (C3), as each complete tag arrives
  sectionsDone: string[];
  degraded: DegradedSource[];
  brief: TriageBrief | null; // set by done
  error: ErrorEvent | null; // set by error
};

export const emptyBrief = (): BriefState =>
  ({ text: "", citations: {}, sectionsDone: [], degraded: [], brief: null, error: null });

export function applyEvent(state: BriefState, event: string, data: any): BriefState { // eslint-disable-line @typescript-eslint/no-explicit-any
  switch (event) {
    case "degraded_source":
      return { ...state, degraded: [...state.degraded, data as DegradedSource] };
    case "token":
      return { ...state, text: state.text + data.text };
    case "citation":
      return state.citations[data.tag] ? state : { ...state, citations: { ...state.citations, [data.tag]: data } };
    case "section_complete":
      return { ...state, sectionsDone: [...state.sectionsDone, data.section] };
    case "done":
      return { ...state, brief: data as TriageBrief };
    case "error":
      return { ...state, error: data as ErrorEvent };
    default:
      return state; // a newer server may send events this page doesn't know yet
  }
}

/** Server-sent events from a byte stream: `event:` and `data:` lines, a blank line ending each event. */
export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<{ event: string; data: string }> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let event = "message";
  let data: string[] = [];
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true }); // a multi-byte character can be split across chunks
    let newline;
    while ((newline = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, newline).replace(/\r$/, "");
      buffer = buffer.slice(newline + 1);
      if (line === "") {
        if (data.length) yield { event, data: data.join("\n") };
        event = "message";
        data = [];
      } else if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        data.push(line.slice(5).replace(/^ /, ""));
      } // ":" lines are keep-alive comments
    }
  }
}

/** Streams an incident's latest triage, calling onEvent for each event until done or error, or until aborted. */
export async function streamTriage(incidentId: string, onEvent: (event: string, data: unknown) => void,
                                   signal?: AbortSignal, baseUrl = ""): Promise<"ok" | "none"> {
  const { response } = await makeApi(baseUrl).GET("/v1/incidents/{incident_id}/triage/stream", {
    params: { path: { incident_id: incidentId } }, parseAs: "stream", signal,
  });
  if (response.status === 404) return "none";
  if (!response.ok || !response.body) throw new Error(`triage stream: HTTP ${response.status}`);
  for await (const { event, data } of parseSse(response.body)) {
    onEvent(event, JSON.parse(data));
    if (event === "done" || event === "error") break;
  }
  return "ok";
}
