# tests/conftest.py
import os
import pytest
import respx
from httpx import AsyncClient
from app import app  # importa seu FastAPI app

@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("MERCOS_WEBHOOK_TOKEN", "SEGREDO")
    monkeypatch.setenv("RD_CLIENT_ID", "cid")
    monkeypatch.setenv("RD_CLIENT_SECRET", "secret")
    monkeypatch.setenv("RD_REFRESH_TOKEN", "rft")
    monkeypatch.setenv("RD_DEFAULT_TAGS", "mercos,cliente_cadastrado")
    monkeypatch.setenv("IDEMPOTENCY_TTL_SECONDS", "3600")
    monkeypatch.setenv("IDEMPOTENCY_MAX_KEYS", "10000")

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mercos_event(email="teste@mercos.com"):
    return [{
        "evento": "cliente.cadastrado",
        "dados": {
            "razao_social": "Cliente Teste",
            "emails": [{"email": email, "tipo": "T", "id": 4}],
            "cidade": "Joinville",
            "estado": "SC",
            "cnpj": "00.000.000/0001-00",
            "telefones": [{"numero": "11999999999"}],
        }
    }]

@pytest.fixture
def rd_urls():
    base = "https://api.rd.services"
    return {
        "token": f"{base}/auth/token",
        "patch": f"{base}/platform/contacts/email:teste@mercos.com",
        "post": f"{base}/platform/contacts",
        "tag": f"{base}/platform/contacts/email:teste@mercos.com/tag",
    }

@pytest.fixture
def rd_token_stub(respx_mock, rd_urls):
    respx_mock.post(rd_urls["token"]).mock(return_value=MockResponse(200, json={"access_token":"at","expires_in":900}))

class MockResponse:
    def __init__(self, status_code, json=None):
        self.status_code = status_code
        self._json = json or {}
        self.headers = {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}: {self._json}")
