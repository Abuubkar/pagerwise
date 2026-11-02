"""Deterministic seed data for the simulated system in data/service_graph.yaml.

  corpus   120 runbooks (12 services x 10 failure modes) and 60 postmortems, rendered from data/templates/ into
           data/corpus/, plus evals/planted_facts.json: one specific, checkable fact per runbook section that has
           one, and each postmortem's root cause, with a question an on-call engineer would ask.
  deploys  30 days of deploys into the deploys table, including the deploys the recent postmortems blame.

Same --seed, same output. Dates are relative to --anchor (default 2026-11-01), not today, so the files don't change
from run to run. docs_mock serves data/corpus/ (and the hand-written data/runbooks/) to the importer.

uv run python scripts/seed.py corpus [--seed 7]
uv run python scripts/seed.py deploys [--seed 7]
"""

import argparse
import asyncio
import hashlib
import json
import random
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from faker import Faker
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy import delete

from pagerwise_api.db import Deploy, SessionLocal, engine
from pagerwise_simulator import Service, load_graph

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"
FACTS = ROOT / "evals" / "planted_facts.json"


@dataclass(frozen=True)
class Mode:
    slug: str
    title: str  # a phrase that reads mid-sentence: "connection pool exhaustion"
    code: str  # used in error codes, e.g. LED-POOL-417
    metric: str  # suffix of the service's metric name
    unit_range: tuple[int, int]  # where this metric's alert threshold falls
    trigger: str
    symptoms: list[str]
    causes: list[tuple[str, str]]
    diagnosis: list[str]
    mitigation: list[str]
    impact_verb: str
    root_causes: list[str]  # postmortem root-cause sentences; {fields} filled per postmortem
    config_keys: list[str]


MODES = [
    Mode("high-latency", "high p99 latency", "LAT", "p99_latency_ms", (600, 2400),
         "the p99 of `{metric}` stays above its threshold for 5 minutes",
         ["p99 rises first; p50 usually stays flat until the problem spreads.",
          "Time spent waiting on {dependency} grows faster than time spent in the service itself.",
          "Request rate is normal: this is slowness, not extra load."],
         [("Slow dependency", "Most latency is spent waiting on {dependency}; check its own latency first."),
          ("Lock contention", "Long-held row or mutex locks serialize requests under normal load."),
          ("Garbage collection pauses", "Heap close to its limit makes collection pauses show up in p99.")],
         ["Compare the service's own processing time with the time spent waiting on {dependency}."],
         ["Shed non-critical traffic with `trafficctl shed {service} --class batch`.",
          "If one dependency explains the latency, follow that dependency's runbook."],
         "was slow",
         ["a slow query plan in {component} after statistics went stale made p99 climb to {peak} ms",
          "{component} held a lock across a network call introduced in {version}, serializing writes"],
         ["request_timeout_ms", "worker_threads", "query_timeout_ms"]),
    Mode("error-rate", "elevated error rate", "ERR", "error_ratio_pct", (2, 15),
         "the share of 5xx responses in `{metric}` stays above its threshold for 5 minutes",
         ["5xx responses rise across all endpoints, not one.", "Retries from callers double the request rate.",
          "Logs show the same error code repeating."],
         [("Bad deploy", "A recent release introduced an exception on a common path."),
          ("Dependency errors passed through", "{dependency} returns errors and the service doesn't degrade."),
          ("Expired credentials", "A rotated secret wasn't picked up and calls to {dependency} are rejected.")],
         ["Group errors by endpoint and by upstream: one endpoint means a code path, all of them means a dependency."],
         ["Roll back the last deploy if it is less than two hours old: `deployctl rollback {service}`.",
          "Turn off the feature flag named in the error, if any."],
         "returned errors",
         ["{version} of {component} sent a null currency on refunds, which the validation layer rejected",
          "a credential for {component} was rotated without restarting consumers, so every call was refused"],
         ["retry_budget_pct", "circuit_breaker_threshold", "max_inflight_requests"]),
    Mode("connection-pool", "connection pool exhaustion", "POOL", "pool_wait_ms", (150, 900),
         "the time requests wait for a database connection, `{metric}`, stays above its threshold for 3 minutes",
         ["Pool `waiting` count is above zero for minutes, not seconds.",
          "Database CPU is normal: the queue is in the application, not the database.",
          "Latency rises before errors do."],
         [("Long transactions holding connections", "A slow code path keeps connections checked out."),
          ("Pool too small for the replica count", "Fewer pods than usual means each pod's pool takes more load."),
          ("Connection leak", "A code path that forgets to return connections after an error.")],
         ["Run `{service}ctl pool stats` on two pods; idle near zero on both confirms exhaustion."],
         ["Scale out: `kubectl -n platform scale deploy/{service} --replicas=+2` (each pod brings its own pool).",
          "Kill transactions open for more than 60 s with `pg_terminate_backend` on {dependency}."],
         "ran out of database connections",
         ["{version} of {component} opened a transaction before calling an external API, holding connections "
          "for up to {peak} ms",
          "a retry loop in {component} leaked one connection per failed attempt until the pool was empty"],
         ["pool_max_size", "pool_checkout_timeout_ms", "statement_timeout_ms"]),
    Mode("memory-pressure", "memory pressure and OOM kills", "MEM", "rss_pct_of_limit", (80, 97),
         "container memory, `{metric}`, stays above its threshold for 10 minutes or a pod is OOM-killed",
         ["Pods restart with reason OOMKilled.", "Memory climbs steadily between restarts: a sawtooth.",
          "Latency spikes right before each restart."],
         [("Unbounded cache", "An in-process cache without a size limit grows with traffic."),
          ("Memory leak in a recent release", "A new code path keeps references to finished requests."),
          ("Large payloads", "A few very large requests allocate far more than usual.")],
         ["Compare memory growth rate before and after the last deploy."],
         ["Raise the memory limit by 25% as a stopgap: `kubectl -n platform set resources deploy/{service}`.",
          "Restart pods in a rolling fashion to buy time."],
         "kept restarting",
         ["a cache added in {version} of {component} had no eviction, growing to {peak} MB per pod",
          "{component} buffered whole export files in memory after a change in {version}"],
         ["cache_max_entries", "max_request_body_kb", "gc_target_pct"]),
    Mode("cpu-saturation", "CPU saturation", "CPU", "cpu_util_pct", (75, 95),
         "CPU utilisation, `{metric}`, stays above its threshold for 10 minutes",
         ["CPU throttling counters rise.", "Latency rises with load in a straight line.",
          "Autoscaler is at its maximum replica count."],
         [("Traffic spike", "Legitimate load above what the current replica count serves."),
          ("Hot loop in a release", "A recent change made a common path far more expensive."),
          ("Noisy neighbour", "Another workload on the same nodes takes CPU.")],
         ["Check whether request rate rose too; if not, look for an expensive code path."],
         ["Raise the autoscaler maximum by 50%.", "Enable the cached response mode if the service has one."],
         "was saturated",
         ["a regex added in {version} of {component} backtracked on long inputs, pinning CPU at {peak}%",
          "{component} recomputed a full price table per request after a cache key change in {version}"],
         ["autoscale_max_replicas", "worker_threads", "cache_ttl_s"]),
    Mode("disk-full", "disk full", "DISK", "disk_used_pct", (80, 95),
         "disk usage, `{metric}`, rises above its threshold",
         ["Writes fail with 'no space left on device'.", "Log volume grew sharply in the last day.",
          "Compaction or cleanup jobs are behind."],
         [("Log volume", "Debug logging left on after an investigation."),
          ("Retention not applied", "A cleanup job failed silently and old data piled up."),
          ("Large temporary files", "A batch job writes temp files it doesn't remove.")],
         ["Find the largest directories with `du -sh /var/lib/{service}/* | sort -h | tail`."],
         ["Delete rotated logs older than 2 days.", "Expand the volume by 50% if cleanup isn't enough."],
         "stopped accepting writes",
         ["debug logging enabled during an earlier incident in {component} was never turned off and filled the disk",
          "the retention job for {component} had failed for {peak} hours after a cron syntax change"],
         ["log_level", "retention_days", "temp_dir_max_gb"]),
    Mode("dependency-timeout", "dependency timeouts", "DEP", "upstream_timeout_pct", (1, 10),
         "the share of calls to a dependency that time out, `{metric}`, stays above its threshold for 5 minutes",
         ["Timeouts concentrate on calls to {dependency}.", "The service's own CPU and memory look normal.",
          "Thread or connection pools fill while waiting."],
         [("Dependency degraded", "{dependency} itself is slow or partially down."),
          ("Timeout set too low", "A recent config change shortened the timeout below normal latency."),
          ("Network path", "Packet loss between zones adds retransmits.")],
         ["Check {dependency}'s own dashboard before changing anything in {service}."],
         ["Open the circuit breaker for {dependency} if the feature can degrade.",
          "Fail over calls to the standby region for {dependency} if one exists."],
         "timed out calling its dependencies",
         ["{component} timed out because its connection to {dependency} pinned to a single failing node",
          "a config change in {version} cut the timeout to {dependency} to below its normal p99"],
         ["upstream_timeout_ms", "circuit_breaker_threshold", "retry_max_attempts"]),
    Mode("bad-deploy", "regression after a deploy", "DEPLOY", "post_deploy_error_pct", (1, 8),
         "errors in the 30 minutes after a deploy, `{metric}`, exceed their threshold",
         ["Errors start within minutes of a deploy finishing.", "Only pods on the new version show errors.",
          "Canary metrics were borderline but passed."],
         [("Code regression", "The new release breaks a path the tests don't cover."),
          ("Config drift", "The release expects a setting that isn't present in production."),
          ("Schema mismatch", "The release reads a column a migration hasn't added yet.")],
         ["Compare error rates between pods on the old and new version."],
         ["Roll back: `deployctl rollback {service}`; don't wait to debug.", "Freeze deploys for {service}."],
         "broke after a deploy",
         ["{version} of {component} read a column that the migration hadn't added in production yet",
          "{version} of {component} renamed a config key, so production fell back to a default of {peak}"],
         ["canary_error_threshold_pct", "deploy_batch_size", "feature_flag_default"]),
    Mode("cert-expiry", "TLS certificate expiry", "TLS", "cert_days_left", (3, 14),
         "a certificate's remaining validity, `{metric}`, drops below its threshold",
         ["Handshake failures from clients with strict validation.", "Errors start at the same minute everywhere.",
          "Internal calls fail while external ones work, or the reverse."],
         [("Renewal job failed", "cert-manager couldn't complete its challenge."),
          ("Pinned intermediate", "A client pins an intermediate that rotated."),
          ("Clock skew", "A node's clock is far enough off to reject valid certificates.")],
         ["Check expiry with `openssl s_client -connect {service}:443 | openssl x509 -noout -enddate`."],
         ["Force renewal: `kubectl -n platform annotate certificate {service} renew=now`.",
          "Restart pods so they load the new certificate."],
         "rejected TLS connections",
         ["the renewal job for {component} failed for {peak} days because its DNS challenge record was deleted",
          "{component} pinned an intermediate certificate that the CA rotated"],
         ["cert_renew_before_days", "tls_min_version", "ocsp_stapling"]),
    Mode("queue-backlog", "queue backlog", "QUEUE", "consumer_lag_msgs", (5000, 90000),
         "consumer lag, `{metric}`, stays above its threshold for 10 minutes",
         ["Consumer lag grows steadily.", "Processing rate is lower than the produce rate.",
          "Downstream data is stale."],
         [("Slow consumers", "Each message takes longer to process than usual."),
          ("Poison message", "One message fails and blocks its partition."),
          ("Too few consumers", "Consumers crashed or were scaled down.")],
         ["Check whether lag grows on all partitions or a few: a few points at a poison message or hot key."],
         ["Scale consumers up to the partition count.", "Skip and dead-letter a poison message after 3 attempts."],
         "fell behind",
         ["a poison message in {component}'s topic blocked partition {peak} for 40 minutes",
          "{version} of {component} made an external call per message, cutting throughput by two thirds"],
         ["consumer_max_poll_records", "consumer_concurrency", "dlq_after_attempts"]),
]


ALERT_SUFFIX = {"high-latency": "LatencyHigh", "error-rate": "ErrorRateHigh", "connection-pool": "PoolExhausted",
                "memory-pressure": "MemoryPressure", "cpu-saturation": "CPUSaturated", "disk-full": "DiskFull",
                "dependency-timeout": "UpstreamTimeouts", "bad-deploy": "PostDeployErrors",
                "cert-expiry": "CertExpiring", "queue-backlog": "ConsumerLagHigh"}


def alert_name(service: str, mode: Mode) -> str:
    """e.g. LedgerPoolExhausted: the alert a runbook is for, and the one a postmortem says opened the incident."""
    return "".join(part.capitalize() for part in service.split("-")) + ALERT_SUFFIX[mode.slug]


def snake(name: str) -> str:
    return name.replace("-", "_")


def callers_of(graph: dict[str, Service], name: str) -> list[str]:
    return sorted(s.name for s in graph.values() if name in s.depends_on)


def corpus(seed: int, anchor: datetime) -> None:
    rng = random.Random(seed)
    fake = Faker()
    fake.seed_instance(seed)
    graph = load_graph()
    env = Environment(loader=FileSystemLoader(ROOT / "data" / "templates"), undefined=StrictUndefined,
                      trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    shutil.rmtree(CORPUS, ignore_errors=True)
    (CORPUS / "runbooks").mkdir(parents=True)
    (CORPUS / "postmortems").mkdir(parents=True)
    facts: list[dict] = []
    used_codes: set[str] = set()

    for service in graph.values():
        view = {"name": service.name, "title": service.name.replace("-", " ").capitalize(), "tier": service.tier,
                "team": service.team, "depends_on": service.depends_on}
        for mode in MODES:
            path = f"data/corpus/runbooks/{service.name}-{mode.slug}.md"
            metric = f"{snake(service.name)}_{mode.metric}"
            threshold = rng.randint(*mode.unit_range)
            minutes = rng.choice([3, 4, 5, 6, 7, 8, 10, 12])
            while (code := f"{service.name[:3].upper()}-{mode.code}-{rng.randint(100, 999)}") in used_codes:
                pass
            used_codes.add(code)
            config_key = rng.choice(mode.config_keys)
            config_value = rng.randint(2, 64) * (10 if "ms" in config_key else 1)
            causes = [{"name": n, "text": t} for n, t in mode.causes]
            rng.shuffle(causes)
            total = rng.randint(8, 30)
            text = env.get_template("runbook.md.j2").render(
                service=view, mode=mode, updated_at=(anchor - timedelta(days=rng.randint(1, 400))).date(),
                alert=alert_name(service.name, mode), metric=metric, callers=callers_of(graph, service.name),
                dependency=(service.depends_on or ["its database"])[0], causes=causes,
                common_share=f"{rng.randint(total // 2 + 1, total)}", common_total=total, error_code=code,
                threshold=threshold, minutes=minutes, config_key=config_key, config_value=config_value,
                escalate_after=rng.choice([15, 20, 30, 45]), customer_impact=rng.choice([5, 10, 20, 25]),
            )
            (ROOT / path).write_text(text)
            heading = f"{view['title']}: {mode.title}"
            facts += [
                {"id": f"rb/{service.name}/{mode.slug}/threshold", "doc": path, "section": f"{heading} > Diagnosis",
                 "question": f"When should {service.name} {mode.title} move to mitigation?",
                 "answer": f"when {metric} stays above {threshold} for {minutes} minutes",
                 "must_contain": [str(threshold), f"{minutes} minutes"]},
                {"id": f"rb/{service.name}/{mode.slug}/error-code", "doc": path, "section": f"{heading} > Diagnosis",
                 "question": f"Which error code does {service.name} log for {mode.title}?",
                 "answer": code, "must_contain": [code]},
                {"id": f"rb/{service.name}/{mode.slug}/config", "doc": path, "section": f"{heading} > Mitigation",
                 "question": f"What config change is the last mitigation step for {service.name} "
                             f"{mode.title}?",
                 "answer": f"set {config_key}={config_value}", "must_contain": [f"{config_key}={config_value}"]},
            ]

    services = list(graph.values())
    for i in range(60):
        service = rng.choice(services)
        mode = rng.choice(MODES)
        recent = i < 8  # the 8 newest fall inside the seeded deploy log, which blames them on a real deploy
        incident = anchor - timedelta(days=rng.randint(2, 28) if recent else rng.randint(35, 540))
        start = incident.replace(hour=rng.randint(1, 23), minute=rng.randint(0, 59))
        component = rng.choice([service.name, *service.depends_on]) if service.depends_on else service.name
        dependency = (service.depends_on or ["its database"])[0]
        version = f"{rng.randint(1, 9)}.{rng.randint(0, 40)}.{rng.randint(0, 20)}"
        peak = rng.randint(12, 4800)
        root_cause = rng.choice(mode.root_causes).format(component=component, version=version, peak=peak,
                                                         dependency=dependency)
        if not root_cause.startswith((component, version)):  # service names and versions stay as written
            root_cause = root_cause[0].upper() + root_cause[1:]
        root_cause += "."
        duration = rng.randint(12, 190)
        alert = alert_name(service.name, mode)
        times = sorted(rng.sample(range(0, duration), 4))
        timeline = [
            ((start - timedelta(minutes=rng.randint(5, 40))).strftime("%H:%M"),
             f"{component} {version} deployed by {fake.name()}." if version in root_cause
             else f"Routine traffic; nothing unusual in {component}."),
            (start.strftime("%H:%M"), f"`{alert}` fired; on-call acknowledged."),
            ((start + timedelta(minutes=times[0])).strftime("%H:%M"), f"Checked the {service.name} runbook for "
                                                                      f"{mode.title}."),
            ((start + timedelta(minutes=times[1])).strftime("%H:%M"), f"Found the cause in {component}."),
            ((start + timedelta(minutes=times[2])).strftime("%H:%M"), "Mitigation applied; error rate falling."),
            ((start + timedelta(minutes=duration)).strftime("%H:%M"), "Recovered; incident resolved."),
        ]
        slug = f"{incident.date()}-{service.name}-{mode.slug}"
        path = f"data/corpus/postmortems/{slug}.md"
        teams = [graph[s].team for s in {service.name, component}]
        text = env.get_template("postmortem.md.j2").render(
            service={"name": service.name}, mode=mode, updated_at=min(incident + timedelta(days=rng.randint(2, 9)), anchor).date(),
            incident_date=incident.date(), title=f"{service.name} {mode.title}", duration=duration,
            summary_cause=f"The cause was in {component}.", severity=rng.choice(["sev1", "sev2", "sev2", "sev3"]),
            alert=alert, failed_pct=rng.randint(2, 60), callers=callers_of(graph, service.name),
            customers=f"{rng.randint(80, 40000):,}", tickets=rng.randint(0, 120), timeline=timeline,
            root_cause=root_cause, component=component,
            factors=[f"The {mode.title} alert for {component} had no runbook link.",
                     rng.choice(["Two teams investigated the same symptom without knowing it",
                                 "The on-call engineer had no access to the database dashboards",
                                 "A recent reorg left the alert routed to the wrong team",
                                 "Logs were sampled at 1%, so the first errors weren't visible"]) + ".",
                     "Dashboards showed averages, which hid the p99."][: rng.randint(2, 3)],
            actions=[{"ticket": f"{snake(service.name).upper()[:4]}-{rng.randint(1000, 9999)}", "team": rng.choice(teams),
                      "text": t} for t in (f"Add an alert on {mode.metric} for {component}.",
                                           f"Add a regression test for: {root_cause[:-1].lower()}.",
                                           "Link the runbook from the alert.")],
        )
        (ROOT / path).write_text(text)
        facts.append({
            "id": f"pm/{slug}", "doc": path, "section": f"Postmortem: {service.name} {mode.title} "
                                                        f"({incident.date()}) > Root cause",
            "question": f"What caused the {service.name} {mode.title} incident on {incident.date()}?",
            "answer": root_cause, "must_contain": [component],
            "cause": {"category": mode.slug, "component": component},
            "deploy": {"service": component, "version": version, "deployed_at": None} if recent and version in root_cause
            else None,
        })
        if facts[-1]["deploy"]:
            facts[-1]["deploy"]["deployed_at"] = timeline[0][0]
            facts[-1]["deploy"]["date"] = str(incident.date())

    FACTS.write_text(json.dumps({"seed": seed, "anchor": anchor.date().isoformat(), "facts": facts}, indent=2) + "\n")
    runbooks, postmortems = len(list((CORPUS / "runbooks").glob("*.md"))), len(list((CORPUS / "postmortems").glob("*.md")))
    print(f"wrote {runbooks} runbooks and {postmortems} postmortems to {CORPUS.relative_to(ROOT)}, "
          f"{len(facts)} planted facts to {FACTS.relative_to(ROOT)}")


async def deploys(seed: int, anchor: datetime) -> None:
    """30 days of deploys before the anchor, replacing whatever is in the table, plus the blamed postmortem deploys."""
    rng = random.Random(seed + 1)
    fake = Faker()
    fake.seed_instance(seed + 1)
    graph = load_graph()
    changes = ["Bump dependencies", "Tune retry policy", "Add metrics for {thing}", "Refactor {thing} client",
               "Fix flaky {thing} handling", "Roll out {thing} behind a flag", "Increase {thing} cache TTL"]
    things = ["checkout", "ledger", "refund", "token", "search", "inventory", "notification", "pool", "retry"]
    rows = []
    for service in graph.values():
        major, minor, patch = rng.randint(1, 9), rng.randint(0, 40), 0
        day = anchor - timedelta(days=30)
        while day < anchor:
            for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
                patch += 1
                at = day.replace(hour=rng.randint(8, 18), minute=rng.randint(0, 59))
                rows.append(Deploy(service=service.name, version=f"{major}.{minor}.{patch}", deployed_at=at,
                                   author=fake.name(), commit_sha=hashlib.sha1(f"{service.name}{patch}{seed}".encode())
                                   .hexdigest(), summary=rng.choice(changes).format(thing=rng.choice(things)),
                                   status="rolled_back" if rng.random() < 0.05 else "succeeded"))
            day += timedelta(days=1)
    blamed = [f["deploy"] for f in json.loads(FACTS.read_text())["facts"] if f.get("deploy")]
    for d in blamed:
        hour, minute = map(int, d["deployed_at"].split(":"))
        at = datetime.fromisoformat(d["date"]).replace(hour=hour, minute=minute, tzinfo=UTC)
        rows.append(Deploy(service=d["service"], version=d["version"], deployed_at=at, author=fake.name(),
                           commit_sha=hashlib.sha1(f"{d['service']}{d['version']}".encode()).hexdigest(),
                           summary=f"Release {d['version']}", status="succeeded"))
    async with SessionLocal() as session:
        await session.execute(delete(Deploy))
        session.add_all(rows)
        await session.commit()
    await engine.dispose()
    print(f"seeded {len(rows)} deploys over 30 days ({len(blamed)} blamed by postmortems)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("what", choices=["corpus", "deploys"])
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--anchor", default="2026-11-01", help="dates are generated relative to this day (UTC)")
    args = parser.parse_args()
    anchor = datetime.fromisoformat(args.anchor).replace(tzinfo=UTC)
    if args.what == "corpus":
        corpus(args.seed, anchor)
    else:
        asyncio.run(deploys(args.seed, anchor))


main()
