#!/usr/bin/env bash
# Compares every contract with a base ref (default origin/main) and fails on a breaking change:
#   REST     contracts/openapi.yaml     oasdiff breaking
#   GraphQL  contracts/schema.graphql   graphql-inspector diff
#   Kafka    contracts/kafka/*.json     BACKWARD compatibility, checked by the compose Redpanda's schema registry
# ALLOW_BREAKING=1 (CI sets it for a PR labelled breaking-change-approved) reports them and passes.
# Needs Docker with `docker compose up -d redpanda`, and npx. Run with `make breaking-check`.
set -uo pipefail
base=${1:-origin/main}
oasdiff=${OASDIFF:-docker run --rm -v $PWD:/specs:ro tufin/oasdiff:v1.35.0}
mkdir -p build/base
broken=()

run() {  # run NAME COMMAND...: a failing command is a breaking change
  local name=$1; shift
  echo "== $name"
  "$@" || broken+=("$name")
}

kafka_backward() {  # the new schema must read everything written with the old one
  local old=$1 new=$2 subject result
  subject="ci-$(basename "$new" .json)-$$"
  docker compose cp "$old" "redpanda:/tmp/$subject.old.json" >/dev/null 2>&1 &&
    docker compose cp "$new" "redpanda:/tmp/$subject.new.json" >/dev/null 2>&1
  result=$(docker compose exec -T redpanda sh -c "
    rpk registry compatibility-level set $subject --level BACKWARD >/dev/null &&
    rpk registry schema create $subject --schema /tmp/$subject.old.json --type json >/dev/null &&
    rpk registry schema check-compatibility $subject --schema /tmp/$subject.new.json --type json \
      --schema-version latest --format json;
    rpk registry subject delete $subject >/dev/null; rpk registry subject delete $subject --permanent >/dev/null")
  echo "$result"
  [[ $result == *'"compatible":true'* ]]  # rpk exits 0 either way
}

git show "$base:contracts/openapi.yaml" > build/base/openapi.yaml
# shellcheck disable=SC2086  # $oasdiff is a command line
run "REST (oasdiff)" $oasdiff breaking --fail-on ERR /specs/build/base/openapi.yaml /specs/contracts/openapi.yaml

git show "$base:contracts/schema.graphql" > build/base/schema.graphql
run "GraphQL (graphql-inspector)" npx --yes @graphql-inspector/cli@7.0.2 diff build/base/schema.graphql \
  contracts/schema.graphql

for schema in contracts/kafka/*.json; do
  if ! git cat-file -e "$base:$schema" 2>/dev/null; then
    echo "== Kafka $schema: new on this branch, nothing to compare"
    continue
  fi
  git show "$base:$schema" > "build/base/$(basename "$schema")"
  run "Kafka $schema (BACKWARD)" kafka_backward "build/base/$(basename "$schema")" "$schema"
done

if (( ${#broken[@]} == 0 )); then
  echo "no breaking changes against $base"
elif [[ ${ALLOW_BREAKING:-0} == 1 ]]; then
  echo "breaking changes, allowed by the breaking-change-approved label: ${broken[*]}"
else
  echo "breaking changes against $base: ${broken[*]} (label the PR breaking-change-approved if intended)"
  exit 1
fi
