# tests/test_idempotency.py
import pytest
import respx

@pytest.mark.asyncio
@respx.mock
async def test_duplicate_event_is_not_reprocessed(client, mercos_event, rd_urls, rd_token_stub):
    # primeira vez: PATCH 200 e TAG 200
    p1 = respx.patch(rd_urls["patch"]).mock(return_value=MockResponse(200, json={"uuid": "u1"}))
    t1 = respx.post(rd_urls["tag"]).mock(return_value=MockResponse(200, json={"ok": True}))

    r1 = await client.post("/webhooks/mercos/clientes?token=SEGREDO", json=mercos_event)
    assert r1.status_code == 200
    assert p1.called
    assert t1.called

    # segunda vez: deve marcar como duplicate e não chamar RD
    p2 = respx.patch(rd_urls["patch"]).mock(return_value=MockResponse(200, json={"uuid": "u1"}))
    t2 = respx.post(rd_urls["tag"]).mock(return_value=MockResponse(200, json={"ok": True}))

    r2 = await client.post("/webhooks/mercos/clientes?token=SEGREDO", json=mercos_event)
    assert r2.status_code == 200
    res = r2.json()["results"][0]
    assert res["status"] == "duplicate"
    assert not p2.called
    assert not t2.called
