# GG Checkout + AbacatePay — Controle de Acesso

Serviço **FastAPI** que integra com o **GG Checkout** (usando **AbacatePay** como gateway) para gerenciar automaticamente o acesso de clientes após pagamento confirmado.

**Sem tela de login ou autenticação própria** — a página de checkout é 100% do GG Checkout. O acesso é liberado automaticamente via webhook após o pagamento ser processado.

---

## Sumário

- [Visão Geral da Arquitetura](#visão-geral-da-arquitetura)
- [Fluxo Completo](#fluxo-completo)
- [Pré-requisitos](#pré-requisitos)
- [Instalação e Configuração](#instalação-e-configuração)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Banco de Dados](#banco-de-dados)
- [Endpoints da API](#endpoints-da-api)
- [Eventos de Webhook](#eventos-de-webhook)
- [Segurança](#segurança)
- [Configurando o GG Checkout](#configurando-o-gg-checkout)
- [Como Integrar no Seu Sistema](#como-integrar-no-seu-sistema)
- [Troubleshooting](#troubleshooting)

---

## Visão Geral da Arquitetura

```
┌─────────────────┐     checkout      ┌─────────────────────┐
│                 │ ───────────────►  │                     │
│    Cliente      │                   │    GG Checkout      │
│                 │ ◄───────────────  │  (AbacatePay gateway)│
└─────────────────┘   confirmação     └──────────┬──────────┘
                                                 │
                                    webhook POST │ /api/v1/webhooks/ggcheckout
                                                 │
                                      ┌──────────▼──────────┐
                                      │                     │
                                      │   Este Serviço      │
                                      │   (FastAPI)         │
                                      │                     │
                                      └──────────┬──────────┘
                                                 │
                                    ┌────────────▼────────────┐
                                    │      PostgreSQL          │
                                    │  customers + payments   │
                                    │  + webhook_events       │
                                    └─────────────────────────┘
                                                 │
                              GET /api/v1/access/check?email=...
                                                 │
                                      ┌──────────▼──────────┐
                                      │   Seu Sistema       │
                                      │   (consulta acesso) │
                                      └─────────────────────┘
```

---

## Fluxo Completo

### 1. Pagamento confirmado (acesso liberado)

```
1. Cliente acessa sua página com link para o GG Checkout
2. Cliente preenche dados e paga (cartão ou PIX via AbacatePay)
3. GG Checkout processa o pagamento e envia:
      POST /api/v1/webhooks/ggcheckout
      { "event": "payment.paid", "payment": { ... }, "product": { ... } }
4. Este serviço valida a assinatura HMAC-SHA256 do webhook
5. Verifica idempotência (evita processar o mesmo evento duas vezes)
6. Cria ou atualiza o cliente no banco (tabela customers)
7. Seta customers.has_access = true e access_granted_at = agora
8. Registra o pagamento (tabela payments, status = PAID)
9. Seu sistema chama GET /api/v1/access/check?email=cliente@email.com
10. Retorna { "has_access": true } → libera o acesso no seu produto
```

### 2. Reembolso ou chargeback (acesso revogado)

```
1. GG Checkout envia:
      { "event": "payment.refunded" }  ou  { "event": "payment.chargeback" }
2. Este serviço valida a assinatura e verifica idempotência
3. Atualiza o pagamento (status = REFUNDED ou CHARGEBACK)
4. Seta customers.has_access = false e access_revoked_at = agora
5. Seu sistema detecta has_access = false e bloqueia o acesso
```

---

## Pré-requisitos

- Python 3.12+
- PostgreSQL 14+ (pode ser local, Docker, Railway, Supabase, Neon etc.)
- Conta no [GG Checkout](https://ggcheckout.com)
- Conta no [AbacatePay](https://abacatepay.com) configurada no GG Checkout

---

## Instalação e Configuração

```bash
# 1. Clonar e entrar no projeto
git clone <repo-url>
cd checkout

# 2. Criar e ativar o ambiente virtual
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows

# 3. Instalar dependências
pip install -r requirements.txt

# 4. Configurar variáveis de ambiente
cp .env.example .env
# Edite o .env com suas credenciais (veja seção abaixo)

# 5. Subir o servidor (as tabelas são criadas automaticamente)
uvicorn app.main:app --reload --port 8000
```

> **Sem banco disponível?** O serviço sobe normalmente e exibe um aviso no log.
> As tabelas são criadas automaticamente assim que o banco estiver acessível e o servidor for reiniciado.

Acesse `http://localhost:8000/docs` para ver a documentação Swagger interativa.

---

## Variáveis de Ambiente

Copie `.env.example` para `.env` e preencha:

| Variável | Obrigatória | Descrição |
|---|---|---|
| `DATABASE_URL` | ✅ | URL de conexão PostgreSQL async. Ex: `postgresql+asyncpg://user:pass@localhost:5432/checkout_db` |
| `GGCHECKOUT_API_KEY` | ✅ | API Key do GG Checkout. Encontre em: **Configurações → MCP / API Key** (formato: `ggck_live_...`) |
| `GGCHECKOUT_API_URL` | ✅ | URL base da API do GG Checkout. Padrão: `https://www.ggcheckout.com/api` |
| `GGCHECKOUT_WEBHOOK_SECRET` | ✅ | Secret HMAC para validação dos webhooks. Configure em: **Configurações → Webhooks → Secret** |
| `APP_BASE_URL` | ✅ | URL pública do seu serviço. Usada para CORS em produção. Ex: `https://seusite.com` |
| `ENVIRONMENT` | ✅ | `development` (CORS aberto, logs DEBUG) ou `production` (CORS restrito, logs INFO) |

### Exemplo de DATABASE_URL por provedor

```bash
# Local / Docker
DATABASE_URL=postgresql+asyncpg://postgres:senha@localhost:5432/checkout_db

# Railway
DATABASE_URL=postgresql+asyncpg://postgres:senha@containers-us-west-X.railway.app:5432/railway

# Supabase (pooler modo session)
DATABASE_URL=postgresql+asyncpg://postgres.XXXX:senha@aws-0-us-east-1.pooler.supabase.com:5432/postgres

# Neon
DATABASE_URL=postgresql+asyncpg://user:senha@ep-XXXX.us-east-2.aws.neon.tech/neondb?ssl=require
```

---

## Estrutura do Projeto

```
checkout/
├── .env.example              # Template de variáveis de ambiente
├── .gitignore
├── requirements.txt          # Dependências Python
├── README.md
└── app/
    ├── __init__.py
    ├── main.py               # Inicialização do FastAPI, lifespan, middlewares
    ├── config.py             # Carregamento de settings via pydantic-settings
    ├── database.py           # Engine async, sessão, create_tables, check_db_connection
    ├── models/
    │   ├── __init__.py
    │   ├── customer.py       # Modelo Customer (email, has_access, timestamps)
    │   └── payment.py        # Modelos Payment e WebhookEvent
    ├── schemas/
    │   ├── __init__.py
    │   └── payment.py        # Schemas Pydantic: webhook payload + respostas da API
    ├── services/
    │   ├── __init__.py
    │   └── ggcheckout.py     # Validação HMAC, chamadas à API do GG Checkout
    └── routers/
        ├── __init__.py
        ├── webhook.py        # POST /webhooks/ggcheckout — processa eventos
        └── access.py         # GET /access/check e /access/payments
```

---

## Banco de Dados

As tabelas são criadas automaticamente na primeira inicialização com banco disponível.

### Tabela `customers`

Armazena cada cliente que realizou ao menos um checkout. Criado automaticamente ao receber o evento `payment.paid`.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | UUID (PK) | Identificador interno |
| `email` | VARCHAR(255) | E-mail do cliente (único, indexado) |
| `name` | VARCHAR(255) | Nome completo (opcional) |
| `document` | VARCHAR(20) | CPF/CNPJ (opcional, indexado) |
| `phone` | VARCHAR(30) | Telefone (opcional) |
| `has_access` | BOOLEAN | `true` = acesso liberado, `false` = bloqueado |
| `created_at` | TIMESTAMPTZ | Data de criação do registro |
| `updated_at` | TIMESTAMPTZ | Data da última atualização |
| `access_granted_at` | TIMESTAMPTZ | Quando o acesso foi liberado pela última vez |
| `access_revoked_at` | TIMESTAMPTZ | Quando o acesso foi revogado pela última vez |

### Tabela `payments`

Cada pagamento registrado via webhook do GG Checkout.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | UUID (PK) | Identificador interno |
| `customer_id` | UUID (FK) | Referência ao cliente (CASCADE DELETE) |
| `ggcheckout_payment_id` | VARCHAR(255) | ID do pagamento no GG Checkout (único, indexado) |
| `ggcheckout_product_id` | VARCHAR(255) | ID do produto no GG Checkout |
| `ggcheckout_product_title` | VARCHAR(500) | Título do produto |
| `amount` | INTEGER | Valor em centavos (ex: `R$ 29,90` = `2990`) |
| `status` | VARCHAR(50) | `PENDING` \| `PAID` \| `REFUNDED` \| `EXPIRED` \| `CHARGEBACK` |
| `payment_method` | VARCHAR(50) | `pix` \| `pix.paid` \| `card` \| `card.paid` |
| `raw_payload` | JSONB | Payload completo do webhook para auditoria |
| `created_at` | TIMESTAMPTZ | Data de criação |
| `paid_at` | TIMESTAMPTZ | Quando foi confirmado como pago |
| `refunded_at` | TIMESTAMPTZ | Quando foi reembolsado/charged back |

### Tabela `webhook_events`

Log de todos os eventos recebidos. Garante idempotência e auditoria completa.

| Coluna | Tipo | Descrição |
|---|---|---|
| `id` | UUID (PK) | Identificador interno |
| `idempotency_key` | VARCHAR(500) | `{payment_id}:{event_type}` — impede reprocessamento (único) |
| `event_type` | VARCHAR(100) | Tipo do evento recebido (indexado) |
| `payload` | JSONB | Payload completo do webhook |
| `processed` | BOOLEAN | `true` se processado com sucesso |
| `processing_error` | TEXT | Mensagem de erro, se houver |
| `received_at` | TIMESTAMPTZ | Quando o evento chegou |
| `processed_at` | TIMESTAMPTZ | Quando foi processado com sucesso |

---

## Endpoints da API

### `POST /api/v1/webhooks/ggcheckout`

Receptor de eventos do GG Checkout. **Não chame este endpoint manualmente** — ele é chamado automaticamente pelo GG Checkout.

**Headers obrigatórios:**
```
Content-Type: application/json
X-Webhook-Signature: sha256=<hmac-hex>
```

**Body (exemplo `payment.paid`):**
```json
{
  "event": "payment.paid",
  "payment": {
    "id": "pay_abc123",
    "status": "paid",
    "method": "card.paid",
    "amount": 2990,
    "customer": {
      "name": "João Silva",
      "email": "joao@email.com",
      "document": "123.456.789-00",
      "phone": "+5511999999999"
    },
    "paidAt": "2024-01-15T14:32:00Z"
  },
  "product": {
    "id": "prod_xyz",
    "title": "Acesso Premium"
  }
}
```

**Respostas:**

| Status | Descrição |
|---|---|
| `200 OK` | `{ "status": "ok" }` — evento processado |
| `200 OK` | `{ "status": "already_processed" }` — evento duplicado ignorado |
| `400 Bad Request` | Payload inválido ou malformado |
| `401 Unauthorized` | Assinatura HMAC inválida ou ausente |

---

### `GET /api/v1/access/check?email={email}`

Verifica se um cliente tem acesso ao sistema. **Este é o endpoint que você chama no seu produto** para saber se o cliente pode acessar o conteúdo.

**Parâmetros:**

| Parâmetro | Tipo | Descrição |
|---|---|---|
| `email` | `string` | E-mail do cliente (query param) |

**Exemplo de requisição:**
```bash
curl "http://localhost:8000/api/v1/access/check?email=joao@email.com"
```

**Resposta — acesso liberado:**
```json
{
  "email": "joao@email.com",
  "has_access": true,
  "access_granted_at": "2024-01-15T14:32:00Z",
  "message": "Acesso liberado. Pagamento confirmado."
}
```

**Resposta — acesso negado (pagamento pendente/reembolsado):**
```json
{
  "email": "joao@email.com",
  "has_access": false,
  "access_granted_at": null,
  "message": "Acesso pendente. Pagamento não confirmado ou reembolsado."
}
```

**Resposta — cliente não encontrado:**
```json
{
  "email": "desconhecido@email.com",
  "has_access": false,
  "access_granted_at": null,
  "message": "Cliente não encontrado. Nenhum pagamento registrado para este e-mail."
}
```

---

### `GET /api/v1/access/payments?email={email}`

Lista todos os pagamentos registrados para um e-mail, em ordem decrescente de data.

**Exemplo de resposta:**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "ggcheckout_payment_id": "pay_abc123",
    "ggcheckout_product_title": "Acesso Premium",
    "amount": 2990,
    "status": "PAID",
    "payment_method": "card.paid",
    "created_at": "2024-01-15T14:30:00Z",
    "paid_at": "2024-01-15T14:32:00Z"
  }
]
```

**Status possíveis:** `PENDING` | `PAID` | `REFUNDED` | `EXPIRED` | `CHARGEBACK`

---

### `GET /health`

Health check simples.

```json
{ "status": "ok", "environment": "development" }
```

---

### `GET /docs` e `GET /redoc`

Documentação interativa Swagger UI e ReDoc, respectivamente. Disponíveis apenas em `development`.

---

## Eventos de Webhook

| Evento | O que acontece no sistema |
|---|---|
| `payment.created` | Ignorado (sem ação) |
| `payment.paid` | ✅ Cliente criado/atualizado, `has_access = true`, pagamento registrado como `PAID` |
| `payment.refunded` | 🔴 `has_access = false`, pagamento marcado como `REFUNDED` |
| `payment.chargeback` | 🔴 `has_access = false`, pagamento marcado como `CHARGEBACK` |
| `payment.expired` | 🟡 Pagamento marcado como `EXPIRED` (acesso não alterado) |

Todos os eventos são registrados na tabela `webhook_events` com o payload completo, independentemente do tipo.

**Idempotência:** Se o GG Checkout enviar o mesmo evento mais de uma vez (retry automático), o sistema detecta pela chave `{payment_id}:{event_type}` e descarta silenciosamente sem reprocessar.

---

## Segurança

### Validação HMAC-SHA256

Cada webhook enviado pelo GG Checkout contém o header:

```
X-Webhook-Signature: sha256=<hex-digest>
```

O serviço valida a assinatura antes de processar qualquer dado:

```python
expected = hmac.new(
    GGCHECKOUT_WEBHOOK_SECRET.encode("utf-8"),
    raw_body,       # body bruto, sem parse
    hashlib.sha256
).hexdigest()

# Comparação segura contra timing attacks
hmac.compare_digest(expected, signature_from_header)
```

Requisições com assinatura inválida ou ausente retornam `401 Unauthorized` imediatamente.

### Considerações adicionais

- O endpoint `/api/v1/access/check` é **público** — qualquer um com o e-mail pode consultar. Se isso for um problema, adicione autenticação (Bearer token, API key etc.) ou remova dados sensíveis da resposta.
- Em produção, configure `ENVIRONMENT=production` para restringir o CORS apenas ao `APP_BASE_URL`.
- Use HTTPS em produção para proteger os payloads dos webhooks em trânsito.

---

## Configurando o GG Checkout

### 1. Configurar o Webhook

1. Acesse **GG Checkout → Configurações → Webhooks → Criar novo**
2. URL do webhook: `https://seudominio.com/api/v1/webhooks/ggcheckout`
3. Selecione os eventos: `payment.paid`, `payment.refunded`, `payment.chargeback`, `payment.expired`
4. Salve e copie o **Secret** gerado
5. Cole o secret em `GGCHECKOUT_WEBHOOK_SECRET` no seu `.env`

### 2. Configurar o AbacatePay como Gateway

1. Acesse **GG Checkout → Gateway Tokens**
2. Selecione **AbacatePay** e cole sua API Key do AbacatePay
3. Salve — o GG Checkout passará a processar pagamentos via AbacatePay automaticamente

### 3. Obter a API Key do GG Checkout

1. Acesse **GG Checkout → Configurações → MCP / API Key**
2. Copie a chave (formato: `ggck_live_...`)
3. Cole em `GGCHECKOUT_API_KEY` no `.env`

---

## Como Integrar no Seu Sistema

### Verificar acesso do usuário (exemplo em Python)

```python
import httpx

async def check_user_access(email: str) -> bool:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://seudominio.com/api/v1/access/check",
            params={"email": email}
        )
        data = response.json()
        return data["has_access"]
```

### Verificar acesso (exemplo em JavaScript/fetch)

```javascript
async function checkAccess(email) {
  const res = await fetch(`https://seudominio.com/api/v1/access/check?email=${encodeURIComponent(email)}`);
  const data = await res.json();
  return data.has_access; // true ou false
}
```

### Fluxo sugerido no seu produto

```
1. Usuário faz login no seu produto (com seu próprio sistema de auth)
2. Ao acessar conteúdo pago, chame GET /api/v1/access/check?email={email}
3. Se has_access = true → exibe o conteúdo
4. Se has_access = false → redireciona para a página de checkout do GG Checkout
```

---

## Troubleshooting

### App não sobe / erro de importação

```bash
# Verifique se o ambiente virtual está ativo
source .venv/bin/activate
pip install -r requirements.txt
```

### "Banco de dados não disponível no startup"

Aviso esperado se o banco ainda não está configurado. O app sobe normalmente.
Quando o banco estiver pronto, preencha `DATABASE_URL` no `.env` e reinicie o servidor.

### Webhook retornando 401

- Verifique se `GGCHECKOUT_WEBHOOK_SECRET` no `.env` é exatamente o mesmo secret configurado no painel do GG Checkout
- Certifique-se de que o body não está sendo modificado antes da validação (proxies/gateways podem alterar o payload)

### Webhook retornando 400

- Verifique se o payload enviado segue o schema esperado (campos `event` e `payment.id` são obrigatórios)
- Consulte o log do servidor para ver o erro de parse detalhado

### Evento processado duas vezes

Não é possível — a idempotência é garantida pelo campo `idempotency_key` com constraint `UNIQUE` no banco. O segundo evento retorna `{ "status": "already_processed" }`.

### Testar localmente com webhook real

Use o [ngrok](https://ngrok.com) para expor o servidor local:

```bash
ngrok http 8000
# Use a URL gerada (ex: https://abc123.ngrok.io) como webhook URL no GG Checkout
```
