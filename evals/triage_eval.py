"""The triage part of the eval: each golden case through the real triage (triage.generate), scored without a model
where possible, plus the judge for citation support. Imported by evals/run.py.

Model calls go through llm.recording: LIVE records them into evals/recordings/, otherwise they're replayed, so an
offline run reproduces the live metrics exactly (latency included: the recordings keep the live timings)."""

import csv
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from metrics import percentile
from pagerwise_api import citations, llm, prompts, triage
from pagerwise_api.db import (
    AlertEvent,
    Chunk,
    Document,
    Incident,
    Service,
    ServiceEdge,
    TriageRun,
)
from pagerwise_api.settings import settings
from pagerwise_docs_mock import DEFAULT_COLLECTIONS, DEFAULT_DEPLOYS, Faults, create_app
from pagerwise_simulator import load_graph
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import seed  # the corpus generator: its failure modes' cause names

EVALS = Path(__file__).resolve().parent
RECORDINGS = EVALS / "recordings"
CALIBRATION = EVALS / "golden" / "calibration.csv"
# The run the labelled rows were drawn from (triage/4 briefs): it gives each row's other citations.
CALIBRATION_BRIEFS = EVALS / "results" / "20261102T182912-dev-v2.json"
JUDGE_MODEL = "llama3.1:8b"  # run.py --judge-model overrides it
KAPPA_MIN = 0.70

# How a brief names each failure category, for root-cause hit@k without a model: the category's own words, plus
# (below) the causes its runbooks list, since "garbage collection pauses" is a correct high-latency diagnosis.
CATEGORY_ALIASES = {
    "high-latency": ["high latency", "p99", "latency", "slow"],
    "error-rate": ["error rate", "5xx", "errors"],
    "connection-pool": ["connection pool", "pool exhaust", "database connections", "connections", "pool"],
    "memory-pressure": ["memory pressure", "oom", "out of memory", "memory leak", "memory"],
    "cpu-saturation": ["cpu saturation", "cpu", "hot loop", "throttl"],
    "disk-full": ["disk full", "disk", "no space left", "log volume"],
    "dependency-timeout": ["dependency timeout", "timing out", "timeouts", "timeout", "upstream"],
    "bad-deploy": ["deploy", "regression", "release", "rollback", "roll back"],
    "cert-expiry": ["certificate", "tls", "cert"],
    "queue-backlog": ["backlog", "consumer lag", "lag", "queue"],
}
for _mode in seed.MODES:  # the runbook template's cause names, e.g. "Lock contention" for high-latency
    CATEGORY_ALIASES[_mode.slug] += [name.lower() for name, _ in _mode.causes]
SHA = re.compile(r"\b[0-9a-f]{7,40}\b")


def _words(text_: str) -> str:
    """Lower case with identifiers split into words: KafkaBrokerLatencyHigh and kafka_broker_p99_latency_ms both
    contain "latency" as a word."""
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text_).replace("_", " ").replace("`", " ").lower()


def named_categories(likely_cause: str) -> list[str]:
    """Categories in the order the Likely cause section first names them; at the same position the longer (more
    specific) phrase wins, so "bad deploy" in an error-rate brief counts once, for the right category."""
    found: dict[str, tuple[int, int]] = {}
    words = _words(likely_cause)
    for category, aliases in CATEGORY_ALIASES.items():
        for alias in aliases:
            for match in re.finditer(r"\b" + re.escape(alias), words):
                key = (match.start(), -len(alias))
                if category not in found or key < found[category]:
                    found[category] = key
    return [c for c, _ in sorted(found.items(), key=lambda item: item[1])]


def cause_hits(likely_cause: str, gold: dict) -> tuple[bool, bool]:
    """(hit@1, hit@3): the gold category is the first (or among the first three) named, and the gold component is
    mentioned at all. INSUFFICIENT_EVIDENCE names nothing."""
    names = named_categories(likely_cause)
    component, words = gold["component"].lower(), _words(likely_cause)
    mentioned = component in words or component.replace("-", " ") in words
    return (mentioned and names[:1] == [gold["category"]], mentioned and gold["category"] in names[:3])


def sentences(section: str) -> list[str]:
    """Lines, then sentences within each line; a numbered step's "1." is a list marker, not a sentence."""
    out = []
    for line in section.splitlines():
        line = re.sub(r"^\s*(\d+\.|[-*])\s+", "", line).strip()
        if not line or line.startswith("```"):
            continue
        out += [p.strip() for p in re.split(r"(?<=[.!?])\s+(?=[A-Z`])", line) if p.strip()]
    return out


def claims(raw: str, evidence: list[dict]) -> list[dict]:
    """Every sentence of the brief with the tags it carries, per section."""
    by_tag = {e["tag"]: e for e in evidence}
    parsed = citations.parse_brief(raw, set(by_tag))
    out = []
    for key, section in parsed.sections.items():
        if section.text in (citations.INSUFFICIENT_EVIDENCE, citations.NO_SIMILAR):
            continue
        for sentence in sentences(section.text):
            tags = [t for t in citations.TAG_RE.findall(sentence) if t in by_tag]
            out.append({"section": key, "sentence": sentence, "claim": citations.TAG_RE.sub("", sentence).strip(),
                        "sources": [{"tag": t, "type": by_tag[t]["source_type"], "text": by_tag[t]["text"]}
                                    for t in dict.fromkeys(tags)]})
    return out


async def prepare_corpus(eval_url: str) -> None:
    """Copies documents and chunks (with their embeddings) from the dev database into the eval database when they differ,
    so triage there retrieves exactly what it would in dev."""
    dev = create_async_engine(settings.database_url)
    target = create_async_engine(eval_url)
    async with dev.connect() as conn:
        dev_shas = set((await conn.execute(select(Document.sha256))).scalars())
    async with target.connect() as conn:
        eval_shas = set((await conn.execute(select(Document.sha256))).scalars())
        eval_v2 = await conn.scalar(select(func.count()).select_from(Chunk).where(Chunk.embedding_v2.is_not(None)))
    if dev_shas != eval_shas or not eval_v2:
        async with dev.connect() as conn:
            docs = [dict(r._mapping) for r in await conn.execute(select(Document.__table__))]
            chunks = [dict(r._mapping) for r in await conn.execute(
                select(*[c for c in Chunk.__table__.c if c.name != "tsv"]))]
        async with target.begin() as conn:
            await conn.execute(text("TRUNCATE documents, chunks CASCADE"))
            await conn.execute(Document.__table__.insert(), docs)
            for i in range(0, len(chunks), 100):
                await conn.execute(Chunk.__table__.insert(), chunks[i : i + 100])
    await dev.dispose()
    await target.dispose()


async def generate_briefs(eval_url: str, cases: list[dict], repeats: int, live: bool) -> list[dict]:
    """Every case `repeats` times, round-robin (so a repeat never follows its own prompt and gets Ollama's prompt
    cache). Returns one record per case and repeat."""
    graph = load_graph()
    engine = create_async_engine(eval_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE incidents, alert_events, triage_runs, services, service_edges CASCADE"))
    async with sessions() as session:
        session.add_all(Service(name=s.name, tier=s.tier, team=s.team) for s in graph.values())
        await session.flush()
        session.add_all(ServiceEdge(from_service=s.name, to_service=d) for s in graph.values() for d in s.depends_on)
        await session.commit()

    golden_deploys = EVALS / "golden" / "deploys.json"
    app = create_app(DEFAULT_COLLECTIONS, deploys=None)
    app.state.docs.deploys = [*create_app(deploys=DEFAULT_DEPLOYS).state.docs.deploys,
                              *create_app(deploys=golden_deploys).state.docs.deploys]
    incidents: dict[str, Incident] = {}
    async with sessions() as session:
        for case in cases:
            opened = datetime.fromisoformat(case["opened_at"])
            incident = Incident(title=case["title"], service=case["service"], severity=case["severity"],
                                summary=case["summary"], opened_at=opened, alert_count=len(case["alerts"]),
                                last_alert_at=opened + timedelta(seconds=max(a["offset_s"] for a in case["alerts"])))
            session.add(incident)
            await session.flush()
            session.add_all(AlertEvent(
                event_id=__import__("uuid").uuid5(__import__("uuid").NAMESPACE_URL, f"triage/{case['id']}/{i}"),
                source="golden", service=a["service"], fingerprint=a["fingerprint"], severity=a["severity"],
                occurred_at=opened + timedelta(seconds=a["offset_s"]), labels={"alertname": a["alertname"]},
                summary=a["summary"], incident_id=incident.id) for i, a in enumerate(case["alerts"]))
            incidents[case["id"]] = incident
        await session.commit()

    records = []
    with llm.recording(RECORDINGS, replay=not live) as recorder:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://deploys") as client:
            for repeat in range(repeats):
                for n, case in enumerate(cases, start=1):
                    app.state.docs.faults = Faults(down=["deploys"] if case["kind"] == "degraded" else [])
                    async with sessions() as session:
                        run = TriageRun(incident_id=incidents[case["id"]].id, incident_version=1, status="running")
                        session.add(run)
                        await session.commit()
                        calls = len(recorder.timings)
                        brief, error = None, None
                        async for name, payload in triage.generate(session, client, run):
                            if name == "done":
                                brief = payload
                            elif name == "error":
                                error = payload
                        timing = recorder.timings[calls] if len(recorder.timings) > calls else (None, None)
                        shown, decision = citations.gate_brief(run.raw_text, triage.cause_tags(run.evidence))
                        records.append({
                            "case": case["id"], "kind": case["kind"], "repeat": repeat,
                            "status": "done" if brief else "error",
                            "error": error.code if error else None, "problems": error.problems if error else [],
                            "verdict": brief.verdict if brief else None,
                            "raw": shown, "model_raw": run.raw_text, "decision": decision,  # raw: the brief as shown
                            "evidence": run.evidence, "degraded": run.degraded_sources,
                            "ttft_ms": timing[0], "total_ms": timing[1],
                            "prompt_tokens": run.prompt_tokens, "output_tokens": run.output_tokens,
                        })
                    if live:
                        print(f"  repeat {repeat + 1}/{repeats}, case {n}/{len(cases)} {case['id']}: "
                              f"{records[-1]['status']} {records[-1]['verdict'] or records[-1]['error']}"
                              f" ({(timing[1] or 0) / 1000:.1f}s)", flush=True)
    await engine.dispose()
    return records


def score_briefs(cases: list[dict], records: list[dict]) -> tuple[dict, list[dict]]:
    by_case = {c["id"]: c for c in cases}
    first = [r for r in records if r["repeat"] == 0]
    per_case, hits1, hits3, abstained, honest = [], [], [], [], []
    for r in first:
        case = by_case[r["case"]]
        parsed = citations.parse_brief(r["raw"] or "", {e["tag"] for e in r["evidence"]}) if r["raw"] else None
        likely = parsed.sections["likely_cause"].text if parsed and "likely_cause" in parsed.sections else ""
        row = {"case": r["case"], "kind": r["kind"], "status": r["status"], "verdict": r["verdict"],
               "error": r["error"], "likely_cause": likely, "gold": case["gold_cause"],
               "named": named_categories(likely)}
        if case["kind"] == "answerable":
            h1, h3 = cause_hits(likely, case["gold_cause"]) if r["status"] == "done" else (False, False)
            hits1.append(h1)
            hits3.append(h3)
            row |= {"hit_at_1": h1, "hit_at_3": h3}
        elif case["kind"] == "unanswerable":
            abstained.append(r["verdict"] == "INSUFFICIENT_EVIDENCE")
            row["abstained"] = abstained[-1]
        else:
            shas = {case["deploy"]["commit_sha"]} | {d["commit_sha"] for d in []}
            deploy_tags = [e["tag"] for e in r["evidence"] if e["source_type"] == "deploy"
                           and f"[{e['tag']}]" in (r["raw"] or "")]
            leaked = [s for s in SHA.findall(r["raw"] or "") if any(full.startswith(s) for full in shas)]
            honest.append(not deploy_tags and not leaked and "deploys" in [d["source"] for d in r["degraded"]])
            row |= {"honest": honest[-1], "deploy_lines": [line.strip() for line in (r["raw"] or "").splitlines()
                                                           if re.search(r"\bdeploy", line, re.IGNORECASE)]}
        per_case.append(row)
    ttfts = [r["ttft_ms"] for r in records if r["ttft_ms"] is not None]
    totals = [r["total_ms"] for r in records if r["total_ms"] is not None]
    out_tokens = sum(r["output_tokens"] or 0 for r in records)
    mean = lambda xs: sum(xs) / len(xs) if xs else 0.0
    metrics = {
        "triage.root_cause_hit_at_1": mean(hits1),
        "triage.root_cause_hit_at_3": mean(hits3),
        "triage.abstention": mean(abstained),
        "triage.degraded_honesty": mean(honest),
        "triage.format_validity": mean([r["status"] == "done" or r["error"] != "format_invalid" for r in first]),
        "triage.ttft_p50_ms": percentile(ttfts, 50), "triage.ttft_p95_ms": percentile(ttfts, 95),
        "triage.total_p50_ms": percentile(totals, 50), "triage.total_p95_ms": percentile(totals, 95),
        "triage.output_tokens_per_s": out_tokens / (sum(totals) / 1000) if totals else 0.0,
        "triage.briefs": len(records),
    }
    return metrics, per_case


def _case(case_id: str) -> dict:
    if not _CASES:
        for kind in ("answerable", "unanswerable", "degraded"):
            _CASES.update({c["id"]: c for c in json.loads((EVALS / "golden" / f"{kind}.json").read_text())["cases"]})
    return _CASES[case_id]


_CASES: dict[str, dict] = {}
DEPLOYED_AT = re.compile(r"deployed at (\S+?)Z? by")


def incident_context(case_id: str) -> str:
    """What the judge knows about the incident a sentence is about: enough to tell "shortly before" from "after"."""
    case = _case(case_id)
    return f"{case['service']}, started {case['opened_at']}"


def with_deploy_timing(source: str, case_id: str) -> str:
    """A deploy record plus how long before or after the incident's start it was: small models misread timestamps
    (calibration showed 08:08 taken as before 07:55), so the arithmetic is done here."""
    match = DEPLOYED_AT.search(source)
    if not match or "before the incident opened" in source:  # triage already states it (since triage/5)
        return source
    deployed = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
    minutes = round((datetime.fromisoformat(_case(case_id)["opened_at"]) - deployed).total_seconds() / 60)
    when = f"{minutes} minutes before" if minutes >= 0 else f"{-minutes} minutes after"
    return f"{source} (This deploy was {when} the incident started.)"


def supported(facts: list[dict], cites: int) -> bool:
    """The judge's yes/no, from its per-fact statuses. Any contradicted fact: no. A sentence citing one source needs
    every fact stated by it; one citing several needs this source to state at least one (the others may carry the
    rest). A sentence with no checkable fact isn't supported by anything."""
    statuses = [f["status"] for f in facts]
    if not statuses or "contradicted" in statuses:
        return False
    return "stated" in statuses if cites > 1 else all(s == "stated" for s in statuses)


async def judge(case_id: str, claim: str, source: str, cites: int = 1) -> dict:
    claim = claim if cites < 2 else f"{claim} (this sentence cites {cites} sources)"
    result = await llm.chat(prompts.judge_messages(incident_context(case_id), claim,
                                                 with_deploy_timing(source, case_id)),
                            estimated_prompt_tokens=len(source) // 3 + 600, model=JUDGE_MODEL,
                            format=prompts.JUDGE_SCHEMA)
    try:
        facts = json.loads(result.content)["facts"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return {"supports": False, "facts": [], "reason": f"unparseable judge output: {result.content[:80]}"}
    reason = "; ".join(f"{f['status']}: {f['fact']}" for f in facts if f["status"] != "stated") or "all stated"
    return {"supports": supported(facts, cites), "facts": facts, "reason": reason}


async def calibrate(live: bool, fill: bool = False) -> dict:
    """Judge the hand-labelled rows; Cohen's kappa against the labels decides whether the judge is trusted. Prompt
    changes are tuned on the "tune" rows; the gate is the kappa on the "holdout" rows, which tuning never looks at."""
    from sklearn.metrics import cohen_kappa_score

    rows = list(csv.DictReader(CALIBRATION.open()))
    with llm.recording(RECORDINGS, replay=not live, fill=fill):
        verdicts = [await judge(r["case"], r["claim"], r["source"], int(r["cites"])) for r in rows]
    out = {"judge_model": JUDGE_MODEL, "prompt": prompts.JUDGE_PROMPT_VERSION, "rows": len(rows), "disagreements": []}
    for split in ("tune", "holdout"):
        pairs = [(r["label"] == "yes", bool(v["supports"])) for r, v in zip(rows, verdicts, strict=True)
                 if r["split"] == split]
        labels, predicted = [a for a, _ in pairs], [b for _, b in pairs]
        out[split] = {"rows": len(pairs), "no_labels": labels.count(False),
                      "kappa": cohen_kappa_score(labels, predicted) if pairs else 0.0,
                      "agreement": sum(a == b for a, b in pairs) / len(pairs) if pairs else 0.0}
    out["kappa"] = out["holdout"]["kappa"]
    out["disagreements"] = [{"id": r["id"], "split": r["split"], "label": r["label"], "judge": v["supports"],
                             "reason": v["reason"], "claim": r["claim"][:160]}
                            for r, v in zip(rows, verdicts, strict=True) if (r["label"] == "yes") != bool(v["supports"])]
    return out


# Deterministic citation checks (ADR 0010): the specific content of a sentence (numbers, versions, identifiers,
# commands, error codes) must come from a source it cites or from the incident itself. Local judges couldn't reach
# kappa 0.70 against the hand labels; these checks are measured against the same labels instead.
SPECIFIC = re.compile(
    r"`[^`]+`"                                    # commands, metrics, alert names in backticks
    r"|\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?"            # dates and timestamps, whole
    r"|\bg?dep-\d+\b"                             # deploy ids
    r"|\b[A-Z]{2,}(?:-[A-Z0-9]+)*-\d+\b"          # error codes and tickets: PAY-TLS-723, KAFK-5775
    r"|\b\d+\.\d+\.\d+\b"                        # versions
    r"|\b[0-9a-f]{10}\b"                           # short commit SHAs
    r"|\b[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+\b"      # CamelCase alert names
    r"|\b[a-z0-9]+(?:_[a-z0-9]+)+\b"              # snake_case metric names
    r"|\d[\d,]*(?:\.\d+)?%|\d{1,3}(?:,\d{3})+|\d{2,}"  # percentages, counts, numbers of 2+ digits
)


SERVICES = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, load_graph()), key=len, reverse=True)) + r")(?![\w-])")
# A postmortem describes a past incident (triage prompt rule 7): content taken from one has to be framed as past.
PAST = re.compile(r"\b(?:past|previous(?:ly)?|prior|earlier|histor(?:y|ical|ically)|before|similar|postmortems?|"
                  r"once|last time|ha(?:s|ve|d) (?:previously )?caused|in 20\d\d)\b", re.IGNORECASE)


def _norm(token: str) -> str:
    return " ".join(token.strip("`").replace(",", "").lower().split())


def specific_tokens(claim: str, case_id: str) -> list[str]:
    """The sentence's checkable content: identifiers, numbers, commands and the services it names, minus what the
    incident itself gives (its alert names and summaries, title, service): quoting the incident is allowed whatever
    the sentence cites."""
    case = _case(case_id)
    incident = _norm(" ".join([case["title"], case["summary"], case["service"], case["opened_at"]]
                              + [f"{a['alertname']} {a['instance']} {a['summary']}" for a in case["alerts"]]))
    found = [t for t in map(_norm, SPECIFIC.findall(claim)) if t and t not in incident]
    found += [m for m in SERVICES.findall(claim) if m != case["service"]]
    return list(dict.fromkeys(found))


def deploy_after_start(source: str, case_id: str) -> bool:
    match = DEPLOYED_AT.search(source)
    return bool(match) and (datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
                            > datetime.fromisoformat(_case(case_id)["opened_at"]))


def pair_supported(case_id: str, section: str, claim: str, source: str, others: list[str]) -> bool | None:
    """One (sentence, cited source) pair; `others` are the texts of the sentence's other citations. None when the
    sentence has no checkable content. No if the source is a deploy from after the incident started (it can't be a
    cause), or a postmortem whose content a cause or impact sentence states without framing it as past. Otherwise
    every token must be in one of the cited sources, and this one must hold at least one."""
    if deploy_after_start(source, case_id):
        return False
    tokens = specific_tokens(claim, case_id)
    if not tokens:
        return None
    here = [t for t in tokens if t in _norm(source)]
    if (section in ("likely_cause", "blast_radius") and source.startswith("# Postmortem")
            and any(not SERVICES.fullmatch(t) for t in here) and not PAST.search(claim)):
        return False
    union = _norm(" ".join([source, *others]))
    return bool(here) and all(t in union for t in tokens)


def check_citations(records: list[dict]) -> tuple[dict, list[dict]]:
    """Citation precision: share of checkable (sentence, cited source) pairs that pass pair_supported. Unsupported-
    claim rate: share of Likely cause and Blast radius sentences with no citation, or none that passes."""
    pairs, unsupported, checked, total, after_start, out = [], [], 0, 0, 0, []
    for r in (r for r in records if r["repeat"] == 0 and r["status"] == "done"):
        for claim in claims(r["raw"], r["evidence"]):
            total += 1
            texts = [x["text"] for x in claim["sources"]]
            verdicts = [pair_supported(r["case"], claim["section"], claim["claim"], t, texts[:i] + texts[i + 1:])
                        for i, t in enumerate(texts)]
            after_start += sum(deploy_after_start(t, r["case"]) for t in texts)
            pairs += [v for v in verdicts if v is not None]
            checked += bool(specific_tokens(claim["claim"], r["case"]))
            if claim["section"] in ("likely_cause", "blast_radius"):
                unsupported.append(not texts or not any(v is not False for v in verdicts))
            if False in verdicts:
                out.append({"case": r["case"], "section": claim["section"], "claim": claim["claim"][:200],
                            "tags": [x["tag"] for x in claim["sources"]], "verdicts": verdicts,
                            "tokens": specific_tokens(claim["claim"], r["case"])})
    metrics = {"triage.citation_precision": sum(pairs) / len(pairs) if pairs else 0.0,
               "triage.unsupported_claim_rate": sum(unsupported) / len(unsupported) if unsupported else 0.0,
               "triage.checked_pairs": len(pairs), "triage.checkable_sentence_share": checked / total if total else 0.0,
               "triage.deploy_citations_after_start": after_start}
    return metrics, out


def check_against_labels() -> dict:
    """How far the deterministic pair check agrees with the hand labels (evals/golden/calibration.csv), on the rows
    it can check: the same yardstick the judge failed. It measures the check, not a run: the other citations of each
    labelled sentence come from the briefs the labels were drawn from (CALIBRATION_BRIEFS, first repeat)."""
    from sklearn.metrics import cohen_kappa_score

    records = json.loads(CALIBRATION_BRIEFS.read_text())["briefs"]
    cited = {(r["case"], c["claim"]): [x["text"] for x in c["sources"]]
             for r in records if r["repeat"] == 0 and r["status"] == "done" for c in claims(r["raw"], r["evidence"])}
    out: dict = {"disagreements": [], "uncheckable": []}
    for split in ("tune", "holdout"):
        rows = [r for r in csv.DictReader(CALIBRATION.open()) if r["split"] == split]
        verdicts = [pair_supported(r["case"], r["section"], r["claim"], r["source"],
                                   [t for t in cited.get((r["case"], r["claim"]), []) if t != r["source"]])
                    for r in rows]
        pairs = [(r["label"] == "yes", v) for r, v in zip(rows, verdicts, strict=True) if v is not None]
        out[split] = {"rows": len(rows), "checkable": len(pairs),
                      "agreement": sum(a == b for a, b in pairs) / len(pairs) if pairs else 0.0,
                      "kappa": cohen_kappa_score([a for a, _ in pairs], [b for _, b in pairs]) if pairs else 0.0}
        out["uncheckable"] += [r["id"] for r, v in zip(rows, verdicts, strict=True) if v is None]
        out["disagreements"] += [{"id": r["id"], "split": split, "label": r["label"], "check": v,
                                  "claim": r["claim"][:160], "tokens": specific_tokens(r["claim"], r["case"])}
                                 for r, v in zip(rows, verdicts, strict=True)
                                 if v is not None and (r["label"] == "yes") != v]
    return out


async def score_citations(records: list[dict], live: bool, fill: bool = False) -> tuple[dict, list[dict]]:
    """Citation precision: share of (sentence, cited source) pairs the judge says the source supports. Unsupported-
    claim rate: share of Likely cause and Blast radius sentences with no citation, or none that supports them."""
    pairs, unsupported, judged = [], [], []
    with llm.recording(RECORDINGS, replay=not live, fill=fill):
        for r in (r for r in records if r["repeat"] == 0 and r["status"] == "done"):
            for claim in claims(r["raw"], r["evidence"]):
                verdicts = [await judge(r["case"], claim["claim"], s["text"], len(claim["sources"]))
                            for s in claim["sources"]]
                pairs += [v["supports"] for v in verdicts]
                if claim["section"] in ("likely_cause", "blast_radius"):
                    unsupported.append(not any(v["supports"] for v in verdicts))
                judged.append({"case": r["case"], "section": claim["section"], "claim": claim["claim"],
                               "verdicts": [{"tag": s["tag"], "type": s["type"], **v}
                                            for s, v in zip(claim["sources"], verdicts, strict=True)]})
    metrics = {"judge.citation_precision": sum(pairs) / len(pairs) if pairs else 0.0,
               "judge.unsupported_claim_rate": sum(unsupported) / len(unsupported) if unsupported else 0.0,
               "judge.judged_pairs": len(pairs)}
    return metrics, judged


def projected_minutes(cases: int, repeats: int, judge_pairs_guess: int = 10) -> float:
    """Wall-clock estimate printed before a live run: ~32 s per brief (slice 5's warm runs) and ~3 s per judged
    pair (about 10 per brief), plus 40 calibration rows."""
    return (cases * repeats * 32 + (cases * judge_pairs_guess + 40) * 3) / 60
