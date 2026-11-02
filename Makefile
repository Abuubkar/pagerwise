OASDIFF := docker run --rm -v $(CURDIR):/specs:ro tufin/oasdiff:v1.35.0

.PHONY: codegen contract-check test test-int smoke topics storm web-test eval eval-test golden

# Regenerate everything derived from the contracts. Generated code is never edited by hand.
codegen:
	uv run python -c "from pagerwise_api.graphql import schema; print(schema.as_str())" > contracts/schema.graphql
	uv run openapi-python-client generate --path contracts/openapi.yaml --output-path packages/clients/python \
		--meta uv --overwrite --config contracts/client-config.yaml
	uv run datamodel-codegen --input contracts/kafka/alert.v1.json --input-file-type jsonschema \
		--output-model-type pydantic_v2.BaseModel --target-python-version 3.13 --use-standard-collections \
		--use-union-operator --use-annotated --strict-nullable --formatters builtin --disable-timestamp \
		--custom-file-header '# Generated from contracts/kafka/alert.v1.json by `make codegen`. Do not edit.' \
		--output packages/kafka/src/pagerwise_kafka/alert_v1.py
	cd apps/web && pnpm codegen

# Fails if the running code would break a client generated from contracts/openapi.yaml.
contract-check:
	@mkdir -p build
	uv run python -c "import json; from pagerwise_api.main import app; print(json.dumps(app.openapi(), indent=2))" > build/openapi.emitted.json
	$(OASDIFF) breaking --fail-on ERR /specs/contracts/openapi.yaml /specs/build/openapi.emitted.json

test:
	uv run pytest -m "not integration"

test-int:
	uv run pytest -m integration

web-test:
	cd apps/web && pnpm test && pnpm typecheck

smoke:
	uv run python scripts/smoke.py

topics:
	uv run python scripts/topics.py

storm:
	uv run python scripts/storm.py

# The eval over the golden set (evals/run.py): retrieval and clustering. Not part of `make test`; exits 1 on a
# missed gate. EMBEDDING=v1|v2|dual overrides the chunk embedding (default: settings); BASELINE=evals/baseline.json
# fails on any quality drop over 1.5 points.
eval:
	uv run python evals/run.py --split dev $(if $(EMBEDDING),--embedding $(EMBEDDING)) $(if $(BASELINE),--baseline $(BASELINE))

# The held-out split: only for deciding a change, never for tuning one.
eval-test:
	uv run python evals/run.py --split test $(if $(EMBEDDING),--embedding $(EMBEDDING)) $(if $(BASELINE),--baseline $(BASELINE))

golden:
	uv run python evals/build_golden.py

