import type { BriefState } from "@/lib/triage";

// The brief as markdown sections, each [Cn] tag turned into a numbered footnote that links to its source below.
// Footnotes are numbered in order of first appearance; a tag whose citation event hasn't arrived yet stays as text.
const TAG = /\[(C\d+)\]/g;
const SOURCE_LABEL: Record<string, string> = { runbooks: "Runbooks", postmortems: "Postmortems", deploys: "Deploys" };

function numbering(state: BriefState): Map<string, number> {
  const numbers = new Map<string, number>();
  for (const match of state.text.matchAll(TAG)) {
    if (state.citations[match[1]] && !numbers.has(match[1])) numbers.set(match[1], numbers.size + 1);
  }
  return numbers;
}

function withFootnotes(line: string, numbers: Map<string, number>, key: string) {
  const parts = line.split(TAG); // odd indexes are tags
  return parts.map((part, i) => {
    if (i % 2 === 0) return <span key={`${key}-${i}`}>{part}</span>;
    const n = numbers.get(part);
    return n ? <sup key={`${key}-${i}`}><a href={`#source-${part}`} className="footnote">[{n}]</a></sup>
      : <span key={`${key}-${i}`}>[{part}]</span>;
  });
}

function sections(text: string): { heading: string; body: string[] }[] {
  const found: { heading: string; body: string[] }[] = [];
  for (const line of text.split("\n")) {
    const heading = line.match(/^##\s+(.+?)\s*$/);
    if (heading) found.push({ heading: heading[1], body: [] });
    else if (found.length && line.trim()) found[found.length - 1].body.push(line);
  }
  return found;
}

export function TriageBrief({ state }: { state: BriefState }) {
  const numbers = numbering(state);
  const sources = [...numbers.entries()].map(([tag, n]) => ({ n, tag, citation: state.citations[tag] }));
  return (
    <div className="brief">
      {state.degraded.map(d => (
        <div role="alert" className="banner warn" key={d.source}>
          <strong>{SOURCE_LABEL[d.source] ?? d.source} unavailable</strong> ({d.reason}). This brief makes no claims
          about {d.source}; check them by hand.
        </div>
      ))}
      {state.error && <div role="alert" className="banner bad">Triage failed: {state.error.detail}</div>}
      {sections(state.text).map(({ heading, body }) => (
        <section key={heading}>
          <h3>{heading}</h3>
          {body.map((line, i) => /^\d+\.\s/.test(line)
            ? <p className="step" key={i}>{withFootnotes(line, numbers, `${heading}-${i}`)}</p>
            : <p key={i}>{withFootnotes(line, numbers, `${heading}-${i}`)}</p>)}
        </section>
      ))}
      {sources.length > 0 && (
        <section className="sources" aria-label="Sources">
          <h3>Sources</h3>
          <ol>
            {sources.map(({ n, tag, citation }) => (
              <li id={`source-${tag}`} key={tag} value={n}>
                <span className={`badge ${citation.source_type}`}>{citation.source_type}</span>{" "}
                <code>{citation.source_id.split("/").pop()}</code>
                <blockquote>{citation.chunk_excerpt}</blockquote>
              </li>
            ))}
          </ol>
        </section>
      )}
      {state.brief && (
        <p className="meta">
          {state.brief.verdict === "CAUSE_IDENTIFIED" ? "Cause identified" : "Insufficient evidence"} ·{" "}
          {state.brief.model} · {state.brief.prompt_version} · first token {(state.brief.usage.ttft_ms / 1000).toFixed(1)} s
        </p>
      )}
    </div>
  );
}
