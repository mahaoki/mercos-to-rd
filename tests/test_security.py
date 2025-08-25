# tests/test_security.py
import pytest

@pytest.mark.asyncio
async def test_webhook_requires_token(client):
    r = await client.post("/webhooks/mercos/clientes", json=[])
    assert r.status_code == 401

@pytest.mark.asyncio
async def test_webhook_with_token_ok(client):
    r = await client.post("/webhooks/mercos/clientes?token=SEGREDO", json=[])
    # Lista vazia é 400 (esperado), mas já passou da segurança
    assert r.status_code == 400
