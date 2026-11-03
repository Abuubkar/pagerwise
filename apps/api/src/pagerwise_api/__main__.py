"""Serves the API with telemetry: uv run python -m pagerwise_api [--host 0.0.0.0] [--port 8001]

The same app as `uvicorn pagerwise_api.main:app`, which still works without traces and metrics. Telemetry is set up
here, not on import, so tests that import the app export nothing."""

import argparse

import uvicorn

import pagerwise_telemetry as telemetry
from pagerwise_api.db import engine
from pagerwise_api.main import app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    telemetry.setup("pagerwise-api")
    telemetry.instrument_app(app)
    telemetry.instrument_engine([engine])
    uvicorn.run(app, host=args.host, port=args.port, log_config=None)  # uvicorn's logs go through the JSON handler


if __name__ == "__main__":
    main()
