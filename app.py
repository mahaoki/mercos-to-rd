import os
from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, Header, HTTPException
from pydantic import BaseModel, EmailStr
from dotenv import load_dotenv

from rd_client import RDClient

load_dotenv()

app = FastAPI(title="Mercos → RD Station Webhook")

rd = RDClient(
    client_id=os.environ["RD_CLIENT_ID"],
    client_secret=os.environ["RD_CLIENT_SECRET"],
    refresh_token=os.environ["RD_REFRESH_TOKEN"],
)

MERCOS_WEBHOOK_TOKEN = os.getenv("MERCOS_WEBHOOK_TOKEN")
DEFAULT_TAGS = [t.strip() for t in os.getenv("RD_DEFAULT_TAGS", "").split(",") if t.strip()]

# ---- Modelagem possível do payload (exemplo) ----
class MercosCliente(BaseModel):
    # Ajuste os campos conforme o payload real do Mercos
    # (normalmente vem nome/razao social, email, telefone, documento etc.)
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    documento: Optional[str] = None  # CPF/CNPJ
    fantasia: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    pais: Optional[str] = None

def map_mercos_to_rd(mercos: MercosCliente) -> Dict[str, Any]:
    """
    Mapeia os campos do Mercos para o schema do RD Station Marketing.
    Campos nativos em RD: name, email, personal_phone, mobile_phone, city, state, country, etc.
    Campos extras -> custom_fields (precisam existir no RD).
    """
    body: Dict[str, Any] = {}
    if mercos.nome:
        body["name"] = mercos.nome
    # Phones: você pode escolher um único campo ou separar em personal_phone / mobile_phone.
    if mercos.telefone:
        body["personal_phone"] = mercos.telefone
    if mercos.cidade:
        body["city"] = mercos.cidade
    if mercos.uf:
        body["state"] = mercos.uf
    if mercos.pais:
        body["country"] = mercos.pais

    # Custom fields (crie no RD com as mesmas keys para receberem dados)
    custom_fields = {}
    if mercos.documento:
        custom_fields["documento"] = mercos.documento
    if mercos.fantasia:
        custom_fields["nome_fantasia"] = mercos.fantasia

    if custom_fields:
        body["custom_fields"] = custom_fields

    return body

def validate_webhook_token(token_header: Optional[str]):
    if MERCOS_WEBHOOK_TOKEN:
        if not token_header or token_header != MERCOS_WEBHOOK_TOKEN:
            raise HTTPException(status_code=401, detail="Invalid webhook token")

@app.post("/webhooks/mercos/cliente.cadastrado")
async def mercos_cliente_cadastrado(
    request: Request,
    x_mercos_token: Optional[str] = Header(default=None),  # exemplo de header simples
):
    # 1) (opcional) validação do webhook
    validate_webhook_token(x_mercos_token)

    # 2) lê o JSON enviado pelo Mercos
    payload = await request.json()
    # Alguns envios do Mercos trazem o evento e um objeto "cliente" (ajuste se necessário)
    dados_cliente = payload.get("cliente") or payload

    try:
        cliente = MercosCliente.model_validate(dados_cliente)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Payload inválido: {e}")

    if not cliente.email:
        # Sem email, o PATCH por email não funciona. 
        # Você pode optar por descartar ou enfileirar para tratamento manual.
        raise HTTPException(status_code=400, detail="Cliente sem e-mail: não é possível upsert no RD.")

    # 3) mapeia para RD
    rd_payload = map_mercos_to_rd(cliente)

    # 4) upsert no RD por email
    upserted = await rd.upsert_contact_by_email(cliente.email, rd_payload)

    # 5) acrescenta tags (opcional)
    if DEFAULT_TAGS:
        try:
            await rd.add_tags("email", cliente.email, DEFAULT_TAGS)
        except Exception:
            # não falha o webhook se der erro só ao taguear
            pass

    return {"status": "ok", "contact": upserted}
