import asyncio
import time
from typing import Dict, Any, Optional, List

import httpx


class RDClient:
    """
    Cliente RD Station Marketing (API 2.0) com:
      - Renovação automática do access_token via refresh_token
      - Reuso de conexão (AsyncClient)
      - Retries com backoff para 429/5xx
      - Retry automático após 401 (refresh e reenvio)
    """

    BASE_URL = "https://api.rd.services"
    TOKEN_URL = f"{BASE_URL}/auth/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        timeout: float = 20.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,  # segundos
        user_agent: str = "mercos-rd-integration/1.0",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token

        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.user_agent = user_agent

        self._client: Optional[httpx.AsyncClient] = None

    # ------------- Infra ------------- #

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, headers={"User-Agent": self.user_agent})
        return self._client

    async def aclose(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    # ------------- Auth ------------- #

    async def _refresh_access_token(self):
        client = await self._ensure_client()
        resp = await client.post(
            self.TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        # alguns tenants retornam expires_in (segundos)
        self._expires_at = time.time() + int(data.get("expires_in", 900))

    async def _get_access_token(self) -> str:
        if not self._access_token or time.time() >= self._expires_at - 30:
            await self._refresh_access_token()
        return self._access_token  # type: ignore

    # ------------- HTTP helpers ------------- #

    async def _request(self, method: str, url: str, *, json: Any | None = None) -> httpx.Response:
        """
        Envia requisição com:
          - Bearer token
          - Retry para 429/5xx com backoff exponencial
          - Em caso de 401, tenta 1x refresh + reenvio
        """
        client = await self._ensure_client()
        attempt = 0
        did_refresh = False

        while True:
            token = await self._get_access_token()
            headers = {"Authorization": f"Bearer {token}"}

            try:
                resp = await client.request(method, url, json=json, headers=headers)
            except httpx.HTTPError:
                # Erros de rede também entram no ciclo de retry
                if attempt < self.max_retries:
                    await asyncio.sleep(self._sleep_for_attempt(attempt))
                    attempt += 1
                    continue
                raise

            # 401 - token expirado ou inválido: tenta UMA vez refresh e reenvia
            if resp.status_code == 401 and not did_refresh:
                await self._refresh_access_token()
                did_refresh = True
                # não conta como tentativa de backoff; vamos reenviar já
                continue

            # 429 ou 5xx → backoff/retry
            if resp.status_code in (429, 500, 502, 503, 504):
                if attempt < self.max_retries:
                    await asyncio.sleep(self._sleep_for_attempt(attempt, resp))
                    attempt += 1
                    continue

            return resp

    def _sleep_for_attempt(self, attempt: int, resp: Optional[httpx.Response] = None) -> float:
        """
        Calcula o tempo de espera para retry. Respeita Retry-After (se houver).
        """
        # Retry-After (em segundos ou data http-date)
        if resp is not None:
            ra = resp.headers.get("Retry-After")
            if ra:
                try:
                    return float(ra)
                except ValueError:
                    # se vier um http-date, ignora e usa backoff exponencial simples
                    pass
        # Backoff exponencial com jitter simples
        base = self.backoff_base * (2 ** attempt)
        return base + (0.1 * attempt)

    # ------------- Contacts ------------- #

    async def upsert_contact_by_email(self, email: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        PATCH /platform/contacts/email:{email}
        - Se 404, fallback para POST /platform/contacts (create)
        """
        patch_url = f"{self.BASE_URL}/platform/contacts/email:{email}"
        resp = await self._request("PATCH", patch_url, json=payload)

        if resp.status_code == 404:
            create_url = f"{self.BASE_URL}/platform/contacts"
            payload_with_email = {"email": email, **payload}
            create_resp = await self._request("POST", create_url, json=payload_with_email)
            create_resp.raise_for_status()
            return create_resp.json()

        resp.raise_for_status()
        return resp.json()

    async def add_tags(self, identifier: str, value: str, tags: List[str]) -> Dict[str, Any]:
        """
        POST /platform/contacts/{identifier}:{value}/tag
        - identifier: "email" ou "uuid"
        """
        url = f"{self.BASE_URL}/platform/contacts/{identifier}:{value}/tag"
        resp = await self._request("POST", url, json={"tags": tags})
        resp.raise_for_status()
        return resp.json()

    # (Opcional) utilitário para obter contato — útil para debug/log
    async def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        url = f"{self.BASE_URL}/platform/contacts/email:{email}"
        resp = await self._request("GET", url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
