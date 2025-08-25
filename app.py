import os
import time
import json
import hashlib
from typing import Any, Dict, Optional, List, Tuple

from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

from rd_client import RDClient

load_dotenv()

app = FastAPI(title="Mercos → RD Station Webhook")

# -----------------------------
# RD Station client (OAuth2)
# -----------------------------
rd = RDClient(
    client_id=os.environ["RD_CLIENT_ID"],
    client_secret=os.environ["RD_CLIENT_SECRET"],
    refresh_token=os.environ["RD_REFRESH_TOKEN"],
)

# -----------------------------
# Configurações / Segurança
# -----------------------------
# Token compartilhado recebido via query string: ?token=SEU_SEGREDO
MERCOS_URL_TOKEN = os.getenv("MERCOS_WEBHOOK_TOKEN")

# Tags padrão a aplicar em todos os eventos "não-excluidos"
DEFAULT_TAGS = [t.strip() for t in os.getenv("RD_DEFAULT_TAGS", "").split(",") if t.strip()]

# Idempotência por evento (em memória)
IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "3600"))  # 1 hora
IDEMPOTENCY_MAX_KEYS = int(os.getenv("IDEMPOTENCY_MAX_KEYS", "10000"))
_IDEMPOTENCY_CACHE: Dict[str, float] = {}


# -----------------------------
# Modelos / Helpers
# -----------------------------
class MercosCliente(BaseModel):
    # Campos mais comuns no "dados" do payload do Mercos
    id: Optional[int] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    cnpj: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    pais: Optional[str] = "BR"

    # Coleções
    emails: Optional[List[Dict[str, Any]]] = None
    telefones: Optional[List[Dict[str, Any]]] = None

    # Endereço (opcional)
    cep: Optional[str] = None
    rua: Optional[str] = None
    bairro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None

    def principal_email(self) -> Optional[str]:
        """
        Seleciona o primeiro e-mail válido.
        Estrutura esperada: emails = [{ "email": "x@y.com", "tipo": "T", "id": 4 }, ...]
        """
        if not self.emails:
            return None
        for e in self.emails:
            val = (e or {}).get("email")
            if val:
                return val
        return None

    def principal_telefone(self) -> Optional[str]:
        """
        Seleciona um telefone, se disponível. A estrutura em Mercos pode variar.
        Exemplos comuns:
          telefones = [{ "numero": "11999999999", "tipo": "M" }, ...]
        """
        if not self.telefones:
            return None
        for t in self.telefones:
            # tenta alguns nomes comuns
            for key in ("numero", "telefone", "fone"):
                val = (t or {}).get(key)
                if val:
                    return str(val)
        return None


def map_mercos_to_rd(mercos: MercosCliente) -> Dict[str, Any]:
    """
    Mapeia 'dados' do Mercos → payload do RD Station (contacts).
    Campos nativos: name, personal_phone, city, state, country, etc.
    Campos extras: custom_fields (precisam existir no RD com esses 'keys').
    """
    body: Dict[str, Any] = {}

    # Nome: usamos a razão social como name principal
    if mercos.razao_social:
        body["name"] = mercos.razao_social

    # Telefone
    tel = mercos.principal_telefone()
    if tel:
        body["personal_phone"] = tel

    # Localidade
    if mercos.cidade:
        body["city"] = mercos.cidade
    if mercos.estado:
        body["state"] = mercos.estado
    if mercos.pais:
        body["country"] = mercos.pais

    # Campos customizados
    custom_fields: Dict[str, Any] = {}
    if mercos.cnpj:
        custom_fields["cnpj"] = mercos.cnpj
    if mercos.nome_fantasia:
        custom_fields["nome_fantasia"] = mercos.nome_fantasia

    # Endereço (opcional, caso queira salvar em custom_fields)
    if mercos.cep:
        custom_fields["cep"] = mercos.cep
    if mercos.rua:
        custom_fields["rua"] = mercos.rua
    if mercos.bairro:
        custom_fields["bairro"] = mercos.bairro
    if mercos.numero:
        custom_fields["numero"] = mercos.numero
    if mercos.complemento:
        custom_fields["complemento"] = mercos.complemento

    if custom_fields:
        body["custom_fields"] = custom_fields

    return body


def _clean_idempotency_cache(now: float) -> None:
    """Remove entradas antigas e limita o tamanho do cache."""
    if not _IDEMPOTENCY_CACHE:
        return
    # TTL
    expired = [k for k, ts in _IDEMPOTENCY_CACHE.items() if now - ts > IDEMPOTENCY_TTL_SECONDS]
    for k in expired:
        _IDEMPOTENCY_CACHE.pop(k, None)
    # Limita tamanho (remove mais antigos primeiro)
    if len(_IDEMPOTENCY_CACHE) > IDEMPOTENCY_MAX_KEYS:
        overflow = len(_IDEMPOTENCY_CACHE) - IDEMPOTENCY_MAX_KEYS
        for k, _ in sorted(_IDEMPOTENCY_CACHE.items(), key=lambda kv: kv[1])[:overflow]:
            _IDEMPOTENCY_CACHE.pop(k, None)


def _idempotency_key_for_event(event_item: Dict[str, Any]) -> str:
    """Gera uma chave idempotente (sha256) para um item do array de eventos."""
    # Usa dump estável (chaves ordenadas) para mesmo evento gerar a mesma assinatura
    serialized = json.dumps(event_item, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _mark_processed(key: str) -> None:
    _IDEMPOTENCY_CACHE[key] = time.time()
    _clean_idempotency_cache(_IDEMPOTENCY_CACHE[key])


def _unmark_processed(key: str) -> None:
    _IDEMPOTENCY_CACHE.pop(key, None)


# -----------------------------
# Healthcheck
# -----------------------------
@app.get("/health")
def health():
    return {"ok": True}


# -----------------------------
# Handler geral de eventos de clientes
# -----------------------------
@app.post("/webhooks/mercos/clientes")
async def mercos_clientes(request: Request, token: Optional[str] = None):
    # 1) Validação do token via query string (?token=...)
    if MERCOS_URL_TOKEN:
        if not token or token != MERCOS_URL_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid webhook token")

    # 2) Ler e validar payload (precisa ser uma lista de eventos)
    try:
        body = await request.json()
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"JSON inválido: {e}")

    if not isinstance(body, list) or not body:
        raise HTTPException(status_code=400, detail="Formato inesperado: esperado lista de eventos")

    now = time.time()
    _clean_idempotency_cache(now)

    results: List[Dict[str, Any]] = []

    for item in body:
        evento = (item or {}).get("evento")
        dados = (item or {}).get("dados", {})

        # 3) Idempotência por item
        key = _idempotency_key_for_event(item)
        if key in _IDEMPOTENCY_CACHE and now - _IDEMPOTENCY_CACHE[key] <= IDEMPOTENCY_TTL_SECONDS:
            results.append({"evento": evento, "status": "duplicate", "idempotency_key": key})
            continue  # pula reprocesamento
        # marca preventivamente como processado; se falhar, removemos a marca
        _mark_processed(key)

        try:
            # 4) Normaliza cliente
            cliente = MercosCliente.model_validate(dados)
            email = cliente.principal_email()
            if not email:
                _unmark_processed(key)
                results.append({"evento": evento, "status": "ignored", "reason": "sem email"})
                continue

            rd_payload = map_mercos_to_rd(cliente)

            # 5) Roteia por tipo de evento
            if evento in ("cliente.cadastrado", "cliente.atualizado", "cliente.bloqueioatualizado"):
                upserted = await rd.upsert_contact_by_email(email, rd_payload)

                # Aplica tags padrão + tag do evento
                tags_to_add = []
                if DEFAULT_TAGS:
                    tags_to_add.extend(DEFAULT_TAGS)
                # Tag do nome do evento (para auditoria de origem)
                if evento:
                    tags_to_add.append(evento)

                if tags_to_add:
                    try:
                        await rd.add_tags("email", email, tags_to_add)
                    except Exception:
                        # não falha o processamento por erro ao taguear
                        pass

                results.append({"evento": evento, "status": "ok", "contact": upserted, "idempotency_key": key})

            elif evento == "cliente.excluido":
                # Não há delete oficial no RD. Marcar com tag especial solicitada:
                try:
                    await rd.add_tags("email", email, ["excluido_no_mercos"])
                    results.append({"evento": evento, "status": "tagged_excluded", "idempotency_key": key})
                except Exception as e:
                    _unmark_processed(key)
                    results.append({"evento": evento, "status": "error", "error": str(e)})
            else:
                # Evento não tratado explicitamente
                results.append({"evento": evento, "status": "ignored", "reason": "evento não suportado", "idempotency_key": key})

        except HTTPException:
            # erros já com status correto
            raise
        except Exception as e:
            # Qualquer falha inesperada: liberar chave para permitir retentativa do Mercos
            _unmark_processed(key)
            results.append({"evento": evento, "status": "error", "error": str(e)})

    return {"status": "processed", "results": results}
