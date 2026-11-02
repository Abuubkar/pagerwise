"""Creates the alert topics (alerts.v1, its two retry topics and the DLQ) if they're missing, then lists them.

uv run python scripts/topics.py
"""

import asyncio

from aiokafka.admin import AIOKafkaAdminClient

from pagerwise_api.settings import settings
from pagerwise_kafka import TOPICS, create_topics


async def main() -> None:
    created = await create_topics(settings.kafka_bootstrap)
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_bootstrap)
    await admin.start()
    try:
        described = await admin.describe_topics(list(TOPICS))
    finally:
        await admin.close()
    for topic in described:
        status = "created" if topic["topic"] in created else "exists"
        print(f"{topic['topic']:18} {len(topic['partitions']):>2} partitions  {status}")


asyncio.run(main())
