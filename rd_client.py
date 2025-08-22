import time
import httpx
from typing import Dict, Any, Optional

class RDClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._access_token: Optional[str] = None
        self._expires_at: float = 0.0

    async def _refresh_access_token(self):
        # Doc: OAuth2 com refresh_token para RD Station Marketing. 
        # Endpoint documentado no fluxo de “Obter tokens” e renovação. 
        token_url = "https://api.rd.services/auth/token"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                token_url,
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

    async def upsert_contact_by_email(self, email: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Usa PATCH /platform/contacts/email:{email} para criar/atualizar sem gerar conversão.
        Doc oficial: Atualizar contato pelo email/uuid. 
        """
        token = await self._get_access_token()
        url = f"https://api.rd.services/platform/contacts/email:{email}"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.patch(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
        # Se o contato não existir, alguns fluxos recomendam fallback em POST create
        if resp.status_code == 404:
            # Tenta criar
            create_url = "https://api.rd.services/platform/contacts"
            payload_with_email = {"email": email, **payload}
            async with httpx.AsyncClient(timeout=20) as client:
                create_resp = await client.post(
                    create_url, json=payload_with_email,
                    headers={"Authorization": f"Bearer {token}"},
                )
            create_resp.raise_for_status()
            return create_resp.json()

        resp.raise_for_status()
        return resp.json()

    async def add_tags(self, identifier: str, value: str, tags: list[str]) -> Dict[str, Any]:
        token = await self._get_access_token()
        url = f"https://api.rd.services/platform/contacts/{identifier}:{value}/tag"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                url, json={"tags": tags},
                headers={"Authorization": f"Bearer {token}"},
            )
        resp.raise_for_status()
        return resp.json()
