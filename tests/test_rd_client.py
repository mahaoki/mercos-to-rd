# tests/test_rd_client.py
import pytest
import respx
from rd_client import RDClient

BASE = "https://api.rd.services"

@pytest.mark.asyncio
@respx.mock
async def test_401_refresh_and_retry(rd_urls):
    respx.post(rd_urls["token"]).mock(return_value=MockResponse(200, json={"access_token":"at1","expires_in":10}))
    # primeira chamada 401
    respx.patch(rd_urls["patch"]).mock(side_effect=[
        MockResponse(401, json={"error":"expired"}),
        MockResponse(200, json={"uuid":"u3"})
    ])
    async with RDClient("cid","secret","rft") as rd:
        res = await rd.upsert_contact_by_email("teste@mercos.com", {"name":"X"})
        assert res["uuid"] == "u3"

@pytest.mark.asyncio
@respx.mock
async def test_404_then_post_create(rd_urls):
    respx.post(rd_urls["token"]).mock(return_value=MockResponse(200, json={"access_token":"at1","expires_in":10}))
    respx.patch(rd_urls["patch"]).mock(return_value=MockResponse(404, json={"error":"not found"}))
    respx.post(rd_urls["post"]).mock(return_value=MockResponse(201, json={"uuid":"u4"}))

    async with RDClient("cid","secret","rft") as rd:
        res = await rd.upsert_contact_by_email("teste@mercos.com", {"name":"X"})
        assert res["uuid"] == "u4"

@pytest.mark.asyncio
@respx.mock
async def test_429_retry(rd_urls):
    respx.post(rd_urls["token"]).mock(return_value=MockResponse(200, json={"access_token":"at1","expires_in":10}))
    calls = [
        MockResponse(429, json={"error":"rate limit"}),
        MockResponse(200, json={"uuid":"u5"})
    ]
    respx.patch(rd_urls["patch"]).mock(side_effect=calls)
    async with RDClient("cid","secret","rft", backoff_base=0.01) as rd:
        res = await rd.upsert_contact_by_email("teste@mercos.com", {"name":"X"})
        assert res["uuid"] == "u5"
