# tests/test_event_flow.py
import pytest
import respx

@pytest.mark.asyncio
@respx.mock
async def test_cadastrado_upsert_and_tag(client, mercos_event, rd_urls, rd_token_stub):
    # 1) PATCH 200 direto
    respx.patch(rd_urls["patch"]).mock(return_value=MockResponse(200, json={"uuid": "u1"}))
    respx.post(rd_urls["tag"]).mock(return_value=MockResponse(200, json={"tags": ["mercos","cliente_cadastrado","cliente.cadastrado"]}))

    r = await client.post("/webhooks/mercos/clientes?token=SEGREDO", json=mercos_event)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "processed"
    assert data["results"][0]["status"] == "ok"
    assert data["results"][0]["contact"]["uuid"] == "u1"

@pytest.mark.asyncio
@respx.mock
async def test_upsert_fallback_post_create(client, mercos_event, rd_urls, rd_token_stub):
    # 404 no PATCH → POST create 201
    respx.patch(rd_urls["patch"]).mock(return_value=MockResponse(404, json={"error":"not found"}))
    respx.post(rd_urls["post"]).mock(return_value=MockResponse(201, json={"uuid": "u2"}))
    respx.post(rd_urls["tag"]).mock(return_value=MockResponse(200, json={"ok": True}))

    r = await client.post("/webhooks/mercos/clientes?token=SEGREDO", json=mercos_event)
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["status"] == "ok"
    assert res["contact"]["uuid"] == "u2"

@pytest.mark.asyncio
@respx.mock
async def test_cliente_excluido_add_tag_only(client, mercos_event, rd_urls, rd_token_stub):
    # troca tipo do evento
    mercos_event[0]["evento"] = "cliente.excluido"
    # apenas chama TAG
    respx.post(rd_urls["tag"]).mock(return_value=MockResponse(200, json={"ok": True}))

    r = await client.post("/webhooks/mercos/clientes?token=SEGREDO", json=mercos_event)
    assert r.status_code == 200
    res = r.json()["results"][0]
    assert res["status"] == "tagged_excluded"
