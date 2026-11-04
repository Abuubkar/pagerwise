---
status: accepted
date: 2026-11-03
---

# CI/CD: GitHub Actions checks, signed multi-arch images on GHCR

**Two workflows.** `ci.yml` runs on every pull request and push to main: lint, contracts, unit, integration,
migrations, web, eval-offline, and load-smoke when the consumer or the Kafka code changes. `release.yml` runs on
main and `v*` tags. It builds images, scans them, pushes them to GHCR with an SBOM and a provenance attestation,
and signs them. Every action is pinned to a commit SHA, with the tag in a comment. Tags can be moved:
aquasecurity/trivy-action's tags were rewritten to credential-stealing code in March 2026 (CVE-2026-33634), so
trivy-action is pinned at v0.36.0, released after the incident. Workflows default to `permissions: {}`, and each
job asks for what it uses. Checkouts don't keep the token. No workflow calls a model: there is no GPU on the
runners, so live evals stay local, and their REPORT.md and baseline.json are committed.

**Lint.**
- **Python:** ruff runs with its default rules at 120 columns. The annotation rules would add about 160 findings,
  mostly return types on tests, and mypy already checks types. mypy runs on the apps and packages. The 74 ruff
  and 30 mypy findings already on main are fixed, with no behaviour change. aiokafka ships no type information, so
  it has an override.
- **Web:** eslint 10 with `eslint-config-next` (core web vitals and typescript), following the Next 16 docs (`next
  lint` is gone). Some plugins inside eslint-config-next don't list ESLint 10 as a peer yet, so pnpm warns; ESLint
  9 is deprecated, so the warnings are the lesser cost.
- **Workflows:** actionlint, run from its pinned container image.
- `make lint` runs the same checks locally.

**Contracts.** Generated clients must match a fresh `make codegen`, and the app must match
`contracts/openapi.yaml` (`make contract-check`, as before). Then `make breaking-check` compares each contract with
the base branch:

| Contract | Check |
|---|---|
| REST | oasdiff |
| GraphQL | graphql-inspector |
| Kafka JSON Schemas | BACKWARD compatibility, checked by the schema registry built into the compose Redpanda |

For Kafka, the base version is registered and the new one checked against it; rpk exits 0 either way, so the
script reads its JSON verdict. This needs no new tool. A standalone JSON-schema diff tool was the alternative, but
it would be one more dependency and wouldn't apply the compatibility rules a registry enforces. A PR labelled
`breaking-change-approved` reports breaking changes and passes; the label also reruns the checks.

**Migrations.** The job runs up, down and up against pgvector Postgres. squawk lints the offline SQL of the
migrations the PR adds (`make migration-lint`). The existing ones have already run and can't change, and on them
squawk reports 81 findings. The label also covers squawk: a deliberate step like 0011's column drop is flagged by
design.

**eval-offline: known misses are reported, not failed.**
- **What runs:** retrieval and clustering run for real. The corpus is imported through docs_mock and the indexer
  with fastembed's models, which actions/cache keeps between runs. Triage replays `evals/recordings`.
- **What fails the job:** main already misses four triage gates (ADR 0010). So with `--baseline`, a gate the
  baseline also misses is printed as `MISSED … (also on the baseline)` and doesn't fail the run. A new miss, or a
  quality drop of more than 1.5 points against main's `evals/baseline.json`, still fails. No threshold changed.
  Failing on every miss would turn every PR red until triage meets its gates.
- **The PR comment:** a sticky comment shows the metrics against main, with deltas. `gh api` updates it in place,
  found by a marker, so no third-party comment action is needed.
- **A replay needs the evidence it was recorded with.** The first CI run missed a recording because the
  local database held a stale copy of 6 postmortems (docs/challenges.md); x86 embeddings changed no prompt. The eval
  now refuses to run when the database's documents differ from `data/`, and a replay miss prints the diff against
  the nearest recording.

**load-smoke** runs `scripts/storm.py` (slice 3's check) at 500 events/s for 60 s, with a replica killed halfway,
against the compose stack. A `git diff` against the base decides whether it runs, instead of a third-party
paths-filter action.

**Images.**
- **Python apps:** one Dockerfile serves all five (`docker/python.Dockerfile`, with `PACKAGE` and `COMMAND`):
  multi-stage, `uv sync --frozen`, non-root (uid 10001). Workspace members install editable, so `/app` keeps the
  repository's layout; docs_mock and the simulator find `data/` relative to their source.
- **Model weights:** `docker/models.Dockerfile` bakes in bge-small, bge-base and the MiniLM reranker (about 0.6
  GB) and sets `HF_HUB_OFFLINE=1`. It is tagged by a hash of the model names in settings.py and the fastembed
  version, and is rebuilt only when that tag isn't in GHCR. api, consumer and indexer use it as their runtime
  base; simulator and docs_mock use plain Python (230 MB, against 1.4 GB).
- **Web:** a standalone Next.js server on node:24-slim. `API_URL` and `NEXT_PUBLIC_GRAPHQL_WS` are build arguments,
  because Next bakes rewrites and public variables into the build.
- **Release pipeline:** each image is first built for amd64 and loaded locally, so trivy scans it before anything
  is pushed. trivy fails on a CRITICAL vulnerability that has a fix; one without a fix can't be acted on and would
  block every release. Then the image is built for amd64 and arm64 with the gha cache, pushed with tags (sha,
  branch, semver), an SBOM and provenance, and signed with cosign keyless. The signature identity is this
  repository's workflow, recorded in the public Rekor log; the repository is public.
- **arm64:** built under QEMU. GitHub's arm64 runners would build natively and faster, but would need a manifest
  merge step; that's worth it if release time becomes a problem.

**Assumptions.**
- GHCR packages are public without any manual step: pushed by this public repository's workflow, all seven allowed
  anonymous pulls (checked 2026-11-04), and each signature verifies with `cosign verify` (docs/runs/slice-07-done-when.txt).
- Branch protection is a ruleset on main requiring these checks, added once their names exist (after the first
  green run).
