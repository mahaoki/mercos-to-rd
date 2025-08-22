# Mercos → RD Station (FastAPI)

Um microserviço em **Python + FastAPI** que recebe o webhook **`cliente.cadastrado`** do **Mercos** e faz **upsert** (cria/atualiza) do contato no **RD Station Marketing** via API 2.0 (OAuth2). Opcionalmente, adiciona **tags** para rastrear a origem.

---

## 🧭 Visão geral

```mermaid
flowchart LR
  A[Mercos Webhook\ncliente.cadastrado] -->|HTTP POST (JSON)| B[FastAPI /webhooks/mercos/cliente.cadastrado]
  B -->|Mapeia campos| C[RDClient]
  C -->|PATCH /platform/contacts/email:{email}\nou POST /platform/contacts| D[RD Station]
  C -->|POST /platform/contacts/{identifier}:{value}/tag| D
```

### O que este serviço faz
- Expõe um endpoint **HTTP POST** para o webhook do Mercos.
- **Valida** um token simples do webhook (header `x-mercos-token`).
- **Converte** o payload do Mercos para o formato de **contato** do RD.
- Executa **upsert** por e-mail no RD (evita duplicidade).
- **Adiciona tags** (ex.: `mercos`, `cliente_cadastrado`).

---

## 📂 Estrutura

```
mercos→rd/
├─ app.py              # API FastAPI (endpoint do webhook)
├─ rd_client.py        # Cliente RD (OAuth2 + endpoints de contato/tag)
├─ requirements.txt
├─ .env.example        # Exemplo de variáveis de ambiente
└─ README.md
```

---

## ✅ Pré‑requisitos
- Python **3.10+**
- Conta RD Station Marketing com acesso à **API 2.0** (OAuth2).
- Acesso ao **Mercos** para configurar o webhook.
- (Opcional) Docker 24+

---

## ⚡ TL;DR (execução rápida)

```bash
# 1) Clonar e entrar na pasta
# git clone <seu-repo> && cd mercos→rd

# 2) Configurar o ambiente
cp .env.example .env
# -> Preencha RD_CLIENT_ID, RD_CLIENT_SECRET, RD_REFRESH_TOKEN
# -> Defina MERCOS_WEBHOOK_TOKEN (segredo compartilhado)

# 3) Instalar e rodar
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# 4) Testar (simulando o Mercos):
curl -X POST http://localhost:8000/webhooks/mercos/cliente.cadastrado   -H 'Content-Type: application/json'   -H 'x-mercos-token: <SEU_TOKEN>'   -d '{
    "cliente": {
      "nome": "Maria da Silva",
      "email": "maria.silva@example.com",
      "telefone": "+55 11 91234-5678",
      "documento": "123.456.789-00",
      "fantasia": "Maria Compras",
      "cidade": "São Paulo",
      "uf": "SP",
      "pais": "BR"
    }
  }'
```

---

## 🔐 Variáveis de ambiente
Crie um arquivo `.env` na raiz (baseado em `.env.example`):

```env
# RD Station Marketing OAuth2
RD_CLIENT_ID=seu_client_id
RD_CLIENT_SECRET=seu_client_secret
RD_REFRESH_TOKEN=seu_refresh_token

# Segurança do webhook do Mercos (header x-mercos-token)
MERCOS_WEBHOOK_TOKEN=um_segredo_que_voce_configura_no_mercos

# Tags automáticas no RD (separadas por vírgula)
RD_DEFAULT_TAGS=mercos,cliente_cadastrado
```

> **Dica:** não faça commit do `.env`. Em produção, injete estes valores no orquestrador (ex.: secrets do Docker/Swarm/K8s ou variáveis no provedor de cloud).

---

## 🔁 Como obter `client_id`, `client_secret` e `refresh_token` (RD)

1. **Crie um App** no RD Station (área de desenvolvedores) e anote **Client ID** e **Client Secret**.
2. Configure um **Redirect URI** (pode ser algo local, ex.: `http://localhost:53330/callback`).
3. Faça o **OAuth2 Authorization Code Flow**:
   - Acesse a URL de autorização do RD com `client_id` e `redirect_uri`.
   - Autorize o app e capture o **`code`** devolvido no redirect.
   - Troque o `code` por **access_token + refresh_token** no endpoint de token do RD.
4. Guarde o **refresh_token** com segurança. O serviço renovará o `access_token` automaticamente (o `rd_client.py` faz o refresh quando necessário).

> O serviço **não** precisa do `access_token` fixo. Ele se auto‑renova com base no `refresh_token`.

---

## 🔔 Configuração do webhook no Mercos
- **URL**: `https://<seu-dominio>/webhooks/mercos/cliente.cadastrado`
- **Método**: `POST`
- **Content-Type**: `application/json`
- **Header secreto**: `x-mercos-token: <MERCOS_WEBHOOK_TOKEN>`
- **Evento**: `cliente.cadastrado` (ajuste conforme sua conta Mercos)
- **Reenvio/retentativas**: habilite se disponível (idempotência por e-mail evita duplicidade no RD)

> Em desenvolvimento, você pode tunelar com **ngrok** para receber webhooks localmente.

---

## 🧩 Mapeamento de campos
O mapeamento padrão está em `app.py → map_mercos_to_rd`.

**Entrada (exemplo Mercos):**
```json
{
  "cliente": {
    "nome": "Maria da Silva",
    "email": "maria.silva@example.com",
    "telefone": "+55 11 91234-5678",
    "documento": "123.456.789-00",
    "fantasia": "Maria Compras",
    "cidade": "São Paulo",
    "uf": "SP",
    "pais": "BR"
  }
}
```

**Saída (payload RD):**
```json
{
  "name": "Maria da Silva",
  "personal_phone": "+55 11 91234-5678",
  "city": "São Paulo",
  "state": "SP",
  "country": "BR",
  "custom_fields": {
    "documento": "123.456.789-00",
    "nome_fantasia": "Maria Compras"
  }
}
```

> **Campos customizados**: crie no RD os campos `documento` e `nome_fantasia` (ou renomeie no código para corresponder aos seus custom fields).

---

## ▶️ Rodando localmente

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

O serviço ficará em `http://localhost:8000`.

**Health check rápido** (sem corpo válido, só para ver se está de pé):
```bash
curl -i http://localhost:8000/docs
```

---

## 🐳 Rodando com Docker (opcional)

**Dockerfile (sugestão):**
```dockerfile
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "4700", "--port", "8000"]
```

**docker run:**
```bash
docker build -t mercos-rd:latest .

docker run --rm -p 8000:8000   -e RD_CLIENT_ID=xxx   -e RD_CLIENT_SECRET=yyy   -e RD_REFRESH_TOKEN=zzz   -e MERCOS_WEBHOOK_TOKEN=segredo   -e RD_DEFAULT_TAGS="mercos,cliente_cadastrado"   mercos-rd:latest
```

**docker-compose.yml (exemplo):**
```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      RD_CLIENT_ID: ${RD_CLIENT_ID}
      RD_CLIENT_SECRET: ${RD_CLIENT_SECRET}
      RD_REFRESH_TOKEN: ${RD_REFRESH_TOKEN}
      MERCOS_WEBHOOK_TOKEN: ${MERCOS_WEBHOOK_TOKEN}
      RD_DEFAULT_TAGS: ${RD_DEFAULT_TAGS}
    restart: unless-stopped
```

---

## 🧪 Testes de integração (cURL)

### 1) Sucesso
```bash
curl -X POST http://localhost:8000/webhooks/mercos/cliente.cadastrado   -H 'Content-Type: application/json'   -H 'x-mercos-token: <SEU_TOKEN>'   -d '{
    "cliente": {
      "nome": "Maria da Silva",
      "email": "maria.silva@example.com",
      "telefone": "+55 11 91234-5678",
      "cidade": "São Paulo",
      "uf": "SP",
      "pais": "BR"
    }
  }'
```

### 2) Token inválido
```bash
curl -X POST http://localhost:8000/webhooks/mercos/cliente.cadastrado   -H 'Content-Type: application/json'   -H 'x-mercos-token: invalido'   -d '{"cliente":{"email":"x@y.com"}}'
# Esperado: HTTP 401
```

### 3) Sem e‑mail (não upserta)
```bash
curl -X POST http://localhost:8000/webhooks/mercos/cliente.cadastrado   -H 'Content-Type: application/json'   -H 'x-mercos-token: <SEU_TOKEN>'   -d '{"cliente":{"nome":"Fulano"}}'
# Esperado: HTTP 400 (Cliente sem e-mail)
```

---

## 🔒 Segurança e conformidade
- **Segredo do webhook**: use `MERCOS_WEBHOOK_TOKEN` e **TLS/HTTPS** em produção.
- **Assinatura/HMAC**: se o Mercos suportar assinatura do corpo, valide timestamp + assinatura (não incluso por padrão).
- **Idempotência**: upsert por e‑mail evita duplicidade em reenvios.
- **LGPD**: defina base legal, política de retenção, consentimento e uso de dados.

---

## 🚀 Produção (boas práticas)
- Execute com um process manager (ex.: `gunicorn` + `uvicorn.workers.UvicornWorker`) atrás de um **reverse proxy** (Nginx/Traefik) com HTTPS.
- Configure **timeout** e **retries** no Mercos, e logs/observabilidade (JSON logs, Sentry, Prometheus, etc.).
- Mantenha `RD_CLIENT_SECRET` e `RD_REFRESH_TOKEN` em **secrets** do orquestrador.

---

## 🧰 Solução de problemas
- **401 no RD**: verifique `client_id/secret/refresh_token` e hora do servidor.
- **404 no PATCH**: o `rd_client.py` faz fallback para `POST /platform/contacts`.
- **422 no webhook**: payload fora do esperado → ajuste o `MercosCliente` e o `map_mercos_to_rd` em `app.py`.
- **Tags não aplicadas**: confirme se o contato existe e tente novamente; o serviço não falha o webhook se o tagging falhar.

---

## 📎 Referências úteis
- Mercos Webhooks (evento `cliente.cadastrado`)
- RD Station Marketing API 2.0 — contatos, tags e OAuth2
- FastAPI, Uvicorn e httpx

---

## 📄 Licença
Uso interno do projeto do cliente. Adapte conforme sua necessidade.
