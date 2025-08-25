# tests/test_payload_validation.py
import pytest

@pytest.mark.asyncio
async def test_payload_must_be_list(client):
    r = await client.post("/webhooks/mercos/clientes?token=SEGREDO", json={"evento": "x"})
    assert r.status_code == 400

@pytest.mark.asyncio
async def test_json_invalido(client):
    # Forçando um body não-JSON
    r = await client.post("/webhooks/mercos/clientes?token=SEGREDO", content=b"{invalid")
    assert r.status_code == 422
