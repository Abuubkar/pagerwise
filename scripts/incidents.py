"""Show the busiest open incidents and the alerts clustering grouped into each: by alert rule and instance.

uv run python scripts/incidents.py [--top 5] [--since-minutes 30]
"""

import argparse
import asyncio

from sqlalchemy import text

from pagerwise_api.db import engine


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--since-minutes", type=int, default=30, help="only incidents opened this recently")
    args = parser.parse_args()
    async with engine.connect() as conn:
        totals = (await conn.execute(text("""
            SELECT count(*) AS incidents, coalesce(sum(alert_count), 0) AS alerts
              FROM incidents WHERE status <> 'resolved' AND opened_at >= now() - make_interval(mins => :m)
        """), {"m": args.since_minutes})).one()
        print(f"{totals.incidents} open incidents from the last {args.since_minutes} minutes, "
              f"grouping {totals.alerts:,} alerts\n")
        incidents = (await conn.execute(text("""
            SELECT id, title, severity, version, alert_count, opened_at, last_alert_at
              FROM incidents WHERE status <> 'resolved' AND opened_at >= now() - make_interval(mins => :m)
             ORDER BY alert_count DESC LIMIT :top
        """), {"m": args.since_minutes, "top": args.top})).all()
        for i in incidents:
            span = (i.last_alert_at - i.opened_at).total_seconds()
            print(f"{i.title}  [{i.severity}, version {i.version}]  {i.alert_count:,} alerts over {span:.0f}s  "
                  f"id {i.id}")
            groups = (await conn.execute(text("""
                SELECT service, labels->>'alertname' AS alertname, labels->>'instance' AS instance,
                       fingerprint, count(*) AS n
                  FROM alert_events WHERE incident_id = :id
                 GROUP BY 1, 2, 3, 4 ORDER BY n DESC
            """), {"id": i.id})).all()
            for g in groups:
                print(f"    {g.n:>6,}  {g.service:16} {g.alertname:26} {g.instance:20} fingerprint {g.fingerprint}")
            print()
    await engine.dispose()


asyncio.run(main())
