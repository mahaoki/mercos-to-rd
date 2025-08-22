# Guia de Execução e Deploy — Mercos → RD Station (FastAPI)

Este guia contém **apenas as instruções** para executar o serviço localmente e em produção (VPS Hostinger) **usando os arquivos `Dockerfile` e `docker-compose.yml` já existentes no projeto**.

---

## 1) Pré-requisitos

- **Domínio** ativo e gerenciável (ex.: `incensofenix.com.br`)
- **Acesso ao DNS** do domínio
- **Conta** RD Station Marketing (API 2.0 / OAuth2 habilitado)
- **Acesso** ao painel do Mercos para configurar Webhook
- **Docker 24+** e **Docker Compose plugin**
- VPS **Ubuntu/Debian** (ex.: Hostinger) com portas **80/443** liberadas

---

## 2) Variáveis de ambiente (.env)

Crie um arquivo `.env` na raiz do projeto (baseado no seu `.env.example`) com:

```env
# RD Station Marketing OAuth2
RD_CLIENT_ID=seu_client_id
RD_CLIENT_SECRET=seu_client_secret
RD_REFRESH_TOKEN=seu_refresh_token

# Segurança do webhook do Mercos (header x-mercos-token)
MERCOS_WEBHOOK_TOKEN=um_segredo_que_voce_configura_no_mercos

# Tags automáticas no RD (opcional, separadas por vírgula)
RD_DEFAULT_TAGS=mercos,cliente_cadastrado

# Produção (Traefik + Let's Encrypt)
DOMAIN=mercos.incensofenix.com.br
TRAEFIK_ACME_EMAIL=seu-email@exemplo.com
```

> **Importante:** não versionar `.env`. Em produção, armazene como **secrets** do orquestrador/host.

---

## 3) Execução local (desenvolvimento)

1. **Configurar `.env`** (ver seção anterior).
2. **Subir com Docker Compose** (arquivos já existem no projeto):

```bash
docker compose up -d --build
```

3. **Testar a API**:
   - Swagger: `http://localhost:8000/docs`
   - Webhook (teste via cURL):
     ```bash
     curl -X POST http://localhost:8000/webhooks/mercos/cliente.cadastrado \
       -H 'Content-Type: application/json' \
       -H 'x-mercos-token: <SEU_TOKEN>' \
       -d '{"cliente":{"nome":"Maria","email":"maria@example.com"}}'
     ```

4. **Logs** (opcional):
```bash
docker compose logs -f
```

---

## 4) Preparar o domínio (DNS)

No gerenciador DNS do seu domínio, crie o **registro A**:

- **Host/Name:** `mercos`
- **Tipo:** A
- **Valor:** IP público do seu VPS (Hostinger)
- **TTL:** automático/300

Ex.: `mercos.incensofenix.com.br → 203.0.113.10`

> Aguarde a propagação (normalmente poucos minutos). Valide com `ping mercos.incensofenix.com.br`.

---

## 5) Preparar o VPS (Hostinger / Ubuntu/Debian)

Conecte via SSH e execute:

```bash
# Atualizar pacotes
sudo apt update && sudo apt upgrade -y

# Instalar Docker + Compose plugin
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# *** Faça logout/login para o grupo 'docker' valer ***
```

Verifique:
```bash
docker --version
docker compose version
```

Crie a pasta do projeto e copie os arquivos (via `git clone`, `scp` ou similar):
```bash
mkdir -p ~/mercos-rd && cd ~/mercos-rd
# copie para cá: .env, Dockerfile, docker-compose.yml, app.py, rd_client.py, etc.
```

> Dica: mantenha **`./letsencrypt/`** (pasta usada pelo Traefik) persistente no VPS para renovação automática do certificado.

---

## 6) Deploy em produção (HTTPS)

1. **Confirme o `.env` de produção** no VPS (com `DOMAIN` e `TRAEFIK_ACME_EMAIL` preenchidos).
2. **Suba os serviços**:
   ```bash
   mkdir -p letsencrypt
   docker compose up -d --build
   ```
3. **Acompanhe logs e emissão de certificado**:
   ```bash
   docker compose logs -f traefik
   docker compose logs -f mercos-rd
   ```

4. **Teste em HTTPS**:
   - Swagger: `https://mercos.incensofenix.com.br/docs`
   - Saúde (acesso): `curl -I https://mercos.incensofenix.com.br/docs`

> O Traefik emite e renova o certificado Let's Encrypt automaticamente para `DOMAIN` (porta 80/443 devem estar liberadas).

---

## 7) Configurar o Webhook no Mercos

No painel do Mercos, cadastre um webhook com:

- **URL**: `https://mercos.incensofenix.com.br/webhooks/mercos/cliente.cadastrado`
- **Método**: `POST`
- **Content-Type**: `application/json`
- **Header**: `x-mercos-token: <MERCOS_WEBHOOK_TOKEN>` (mesmo do `.env`)
- **Evento**: `cliente.cadastrado`

> Se o Mercos suportar reenvio/retentativa, ative. O serviço é idempotente por e-mail (upsert no RD).

---

## 8) Operação e manutenção

- **Logs**:
  ```bash
  docker compose logs -f traefik
  docker compose logs -f mercos-rd
  ```

- **Atualizar versão da app**:
  ```bash
  git pull   # (se estiver versionando)
  docker compose up -d --build
  ```

- **Parar serviços**:
  ```bash
  docker compose down
  ```

- **Backup**:
  - Salve `.env` e a pasta `./letsencrypt/` (certificados).

---

## 9) Troubleshooting

- **DNS ainda não resolve**:
  - Verifique o registro A e a propagação.
  - `ping mercos.incensofenix.com.br` deve responder o IP do VPS.

- **Certificado não é emitido**:
  - Portas 80 e 443 precisam estar liberadas (firewall/segurança do VPS).
  - Verifique `docker compose logs -f traefik` (erros ACME).
  - `DOMAIN` no `.env` deve estar **exatamente** igual ao host público.

- **404/Host mismatch**:
  - Confirme se `DOMAIN` no `.env` bate com o domínio acessado.
  - Reinicie os serviços após alterar `.env` (`docker compose up -d`).

- **401 na API do RD**:
  - Revise `RD_CLIENT_ID`, `RD_CLIENT_SECRET`, `RD_REFRESH_TOKEN`.
  - Cheque horário do servidor (NTP).

- **400/422 no webhook**:
  - Payload fora do esperado → ajustar mapeamento (`map_mercos_to_rd`).
  - Sem e-mail → o upsert por e-mail não é possível (retorna 400).

---

## 10) Endpoint úteis

- **Docs/Swagger**: `https://mercos.incensofenix.com.br/docs`
- **Webhook**: `https://mercos.incensofenix.com.br/webhooks/mercos/cliente.cadastrado`

---

## 11) Boas práticas de produção

- Sempre usar **HTTPS**.
- Proteger `.env` (não versionar, usar secrets).
- Monitorar logs e considerar observabilidade (Sentry/Prometheus).
- Manter `./letsencrypt/` persistente para renovação automática dos certificados.
- Atualizações com **`docker compose up -d --build`** para zero-downtime simples.

---

## 12) Referências rápidas

- Mercos Webhooks (evento `cliente.cadastrado`)
- RD Station API 2.0 (contatos, tags, OAuth2)
- FastAPI (docs)
- Traefik (docs)

---

**Pronto.** Após seguir estes passos, seu serviço deverá estar publicamente acessível em `https://mercos.incensofenix.com.br/docs` e recebendo os eventos do Mercos no endpoint configurado.
