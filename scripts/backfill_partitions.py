"""Step 2 of the alert_events partition migration: copy existing rows into the partitioned shadow.

Run after `alembic upgrade 0006` and before `alembic upgrade 0007`. Safe to stop and rerun: it resumes from the
last batch it finished. See docs/migrations.md.

uv run python scripts/backfill_partitions.py [--batch-size 50000]
"""

import argparse
import asyncio
import time

from pagerwise_api.db import engine
from pagerwise_api.partitions import backfill


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=50_000)
    args = parser.parse_args()
    started = time.monotonic()
    progress = await backfill(engine, args.batch_size, on_batch=lambda copied, upto: print(
        f"  {copied:>9,} rows copied, up to {upto:%Y-%m-%d %H:%M:%S} ({time.monotonic() - started:.1f}s)"))
    await engine.dispose()
    print(f"backfill {'finished' if progress.finished else 'stopped'}: {progress.rows_copied:,} rows in "
          f"{progress.batches} batches this run, {time.monotonic() - started:.1f}s")


asyncio.run(main())
