"""Import runbooks and postmortems from the docs API into Postgres.

uv run python -m pagerwise_indexer [--docs-url http://localhost:8002] [--source runbooks --source postmortems]
"""

import argparse
import asyncio
import logging
import sys

import httpx

from pagerwise_api.db import SessionLocal, engine
from pagerwise_indexer.importer import SOURCE_TYPES, ImportFailed, import_collection


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--docs-url", default="http://localhost:8002")
    parser.add_argument("--source", action="append", choices=list(SOURCE_TYPES))
    args = parser.parse_args()
    status = 0
    async with httpx.AsyncClient(base_url=args.docs_url, timeout=10) as client:
        for source in args.source or list(SOURCE_TYPES):
            try:
                r = await import_collection(client, SessionLocal, source)
            except ImportFailed as e:
                print(f"{source:12} FAILED: {e} (progress saved; rerun to resume)")
                status = 1
                continue
            print(f"{source:12} {r.pages} pages, {r.not_modified} not modified (304), {r.retries} retries, "
                  f"{r.restarts} restarts{', resumed' if r.resumed else ''}; documents: {r.loaded} new, "
                  f"{r.reloaded} changed, {r.unchanged} unchanged; {r.chunks} chunks; {r.seconds:.1f}s")
    await engine.dispose()
    return status


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
sys.exit(asyncio.run(main()))
