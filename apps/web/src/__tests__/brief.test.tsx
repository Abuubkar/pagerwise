import { render, screen, within } from "@testing-library/react";
import { http } from "msw/http";
import { TriageBrief } from "@/components/TriageBrief";
import { TriagePanel } from "@/components/TriagePanel";
import { API, server, sseResponse } from "@/testing";
import { applyEvent, emptyBrief } from "@/lib/triage";

const citation = (tag: string, section: string, source_type = "runbook", source_id = `data/corpus/runbooks/${tag}.md`) =>
  ({ tag, section, source_type, source_id, chunk_id: source_type === "deploy" ? null : "0199aaaa-0000-7000-8000-00000000000" + tag.slice(1),
     chunk_excerpt: `excerpt of ${tag}` });
const TEXT = "## Likely cause\nA deploy of redis-cache 6.38.7 buffered exports in memory [C4][C2].\n\n" +
  "## First steps\n1. Roll back redis-cache [C4].\n2. Check heap usage [C2].\n";
const brief = (degraded: { source: string; reason: string }[] = []) => ({
  triage_id: "t-1", incident_id: "i-1", incident_version: 1, verdict: "CAUSE_IDENTIFIED", model: "qwen3.5:9b-q4_K_M",
  prompt_version: "triage/3", usage: { prompt_tokens: 3000, output_tokens: 250, ttft_ms: 21000, total_ms: 35000 },
  degraded_sources: degraded, sections: {},
});

test("citations render as numbered footnotes linked to their sources", () => {
  let state = applyEvent(emptyBrief(), "token", { text: TEXT });
  state = applyEvent(state, "citation", citation("C4", "likely_cause", "deploy", "dep-0323"));
  state = applyEvent(state, "citation", citation("C2", "likely_cause"));
  render(<TriageBrief state={state} />);

  // Numbered by first appearance: C4 is [1], C2 is [2], wherever they recur.
  const [first, second, again] = screen.getAllByRole("link");
  expect(first).toHaveTextContent("[1]");
  expect(first).toHaveAttribute("href", "#source-C4");
  expect(second).toHaveTextContent("[2]");
  expect(second).toHaveAttribute("href", "#source-C2");
  expect(again).toHaveAttribute("href", "#source-C4");
  const sources = within(screen.getByRole("region", { name: "Sources" })).getAllByRole("listitem");
  expect(sources.map(li => li.id)).toEqual(["source-C4", "source-C2"]);
  expect(sources[0]).toHaveTextContent(/^deploy dep-0323\s*excerpt of C4$/);
  expect(sources[1]).toHaveTextContent(/^runbook C2\.md\s*excerpt of C2$/);
});

test("a tag whose citation hasn't arrived yet stays plain text", () => {
  const state = applyEvent(emptyBrief(), "token", { text: "## Likely cause\nPool exhausted [C9]" });
  render(<TriageBrief state={state} />);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
  expect(screen.getByText("[C9]")).toBeInTheDocument();
});

test("a degraded_source event shows the banner and the brief still renders", async () => {
  const degraded = { source: "deploys", reason: "HTTP 503" };
  server.use(http.get(`${API}/v1/incidents/:id/triage/stream`, () => sseResponse([
    ["degraded_source", degraded],
    ["token", { text: TEXT }],
    ["citation", citation("C2", "likely_cause")],
    ["done", brief([degraded])],
  ])));
  render(<TriagePanel incidentId="i-1" triageId="t-1" baseUrl={API} />);

  const banner = await screen.findByRole("alert");
  expect(banner).toHaveTextContent("Deploys unavailable (HTTP 503). This brief makes no claims about deploys");
  expect(await screen.findByText(/Cause identified/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Likely cause" })).toBeInTheDocument();
});

test("an incident with no triage yet says so", async () => {
  server.use(http.get(`${API}/v1/incidents/:id/triage/stream`, () =>
    Response.json({ code: "not_found" }, { status: 404, headers: { "Content-Type": "application/problem+json" } })));
  render(<TriagePanel incidentId="i-2" triageId={null} baseUrl={API} />);
  expect(await screen.findByText("No triage yet.")).toBeInTheDocument();
});
