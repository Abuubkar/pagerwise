#!/usr/bin/env bash
# Lints the SQL of the migrations added since a base ref (default origin/main) with squawk. Older migrations have
# run already and can't change. ALLOW_BREAKING=1 (the breaking-change-approved label) reports findings and passes:
# a deliberate step such as dropping a column (0011) is flagged by design. Run with `make migration-lint`.
set -euo pipefail
base=${1:-origin/main}
added=$(git diff --name-only --diff-filter=A "$base"...HEAD -- 'apps/api/migrations/versions/*.py' | sort)
if [[ -z $added ]]; then
  echo "no migrations added since $base"
  exit 0
fi
first=$(head -1 <<<"$added")
down=$(sed -nE 's/^down_revision[^=]*= *"([^"]+)".*/\1/p' "$first")
mkdir -p build
uv run alembic upgrade "$down:head" --sql 2>/dev/null > build/migrations.sql
echo "squawk on $(wc -l <<<"$added" | tr -d ' ') added migration(s), from $down to head"
if ! uvx --from squawk-cli==2.71.0 squawk --pg-version 18 build/migrations.sql; then
  [[ ${ALLOW_BREAKING:-0} == 1 ]] && echo "allowed by the breaking-change-approved label" && exit 0
  exit 1
fi
