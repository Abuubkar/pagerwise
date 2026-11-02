import asyncio

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_concurrent_triage_requests_make_one_run_and_one_409(client):
    # Several rounds: one lucky interleaving proves little. Each round races two requests for a fresh incident.
    for round_no in range(5):
        incident = (await client.post("/v1/incidents", json={
            "title": f"Ledger writes failing {round_no}", "service": "ledger", "severity": "sev1",
        })).json()
        url = f"/v1/incidents/{incident['id']}/triage"
        tenant = {"X-Pagerwise-Tenant": f"race-{round_no}"}  # accepted runs keep their slot (no worker here)
        first, second = await asyncio.gather(client.post(url, headers=tenant), client.post(url, headers=tenant))

        by_status = {r.status_code: r for r in (first, second)}
        assert sorted(by_status) == [202, 409], [r.text for r in (first, second)]
        accepted, conflict = by_status[202].json(), by_status[409].json()
        assert conflict["code"] == "triage_in_progress"
        assert conflict["triage_id"] == accepted["triage_id"]  # the loser is pointed at the winner's run
        assert by_status[409].headers["content-type"] == "application/problem+json"


async def test_finished_triage_does_not_block_a_new_one(client):
    from sqlalchemy import text

    incident = (await client.post("/v1/incidents", json={"title": "t", "service": "ledger", "severity": "sev2"})).json()
    url = f"/v1/incidents/{incident['id']}/triage"
    first = (await client.post(url)).json()
    # Finish it the way the stream does; only queued or running runs block a new one.
    async with client.sessions() as session:
        await session.execute(text("UPDATE triage_runs SET status = 'completed' WHERE id = :id"),
                              {"id": first["triage_id"]})
        await session.commit()
    second = await client.post(url)
    assert second.status_code == 202
    assert second.json()["triage_id"] != first["triage_id"]



async def test_a_tenant_at_its_limit_gets_503_with_retry_after(client):
    """The limit is 2 queued or running triages per tenant; another tenant is unaffected."""
    urls = []
    for i in range(4):
        incident = (await client.post("/v1/incidents", json={"title": f"t{i}", "service": "ledger",
                                                             "severity": "sev2"})).json()
        urls.append(f"/v1/incidents/{incident['id']}/triage")
    team = {"X-Pagerwise-Tenant": "team-a"}
    statuses = [(await client.post(url, headers=team)).status_code for url in urls[:2]]
    refused = await client.post(urls[2], headers=team)
    other = await client.post(urls[3], headers={"X-Pagerwise-Tenant": "team-b"})

    assert statuses == [202, 202]
    assert refused.status_code == 503 and refused.json()["code"] == "triage_capacity"
    assert refused.headers["retry-after"] == "30"
    assert other.status_code == 202
    async with client.sessions() as session:  # the refused request left no run behind
        from sqlalchemy import text

        assert await session.scalar(text("SELECT count(*) FROM triage_runs WHERE tenant = 'team-a'")) == 2
