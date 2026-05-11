import uuid
from datetime import datetime
from pydantic import BaseModel


# ── Respostas da API ──────────────────────────────────────────────────────────

class AccessStatusResponse(BaseModel):
    """Status de acesso de um cliente ao sistema."""
    email: str
    has_access: bool
    access_granted_at: datetime | None = None
    message: str


class PaymentResponse(BaseModel):
    """Dados de um pagamento registrado."""
    id: uuid.UUID
    ggcheckout_payment_id: str
    ggcheckout_product_title: str | None
    amount: int | None
    status: str
    payment_method: str | None
    created_at: datetime
    paid_at: datetime | None

    model_config = {"from_attributes": True}


# ── GG Checkout Webhook Schemas ───────────────────────────────────────────────

class GGCheckoutCustomer(BaseModel):
    name: str | None = None
    email: str | None = None
    document: str | None = None
    phone: str | None = None

    model_config = {"extra": "allow"}


class GGCheckoutPaymentData(BaseModel):
    id: str
    status: str          # pending | paid | refunded | expired | chargeback
    method: str | None = None   # pix | pix.paid | card | card.paid
    amount: int | None = None   # em centavos
    customer: GGCheckoutCustomer | None = None
    createdAt: str | None = None
    paidAt: str | None = None
    refundedAt: str | None = None
    expiredAt: str | None = None

    model_config = {"extra": "allow"}


class GGCheckoutProductData(BaseModel):
    id: str | None = None
    title: str | None = None

    model_config = {"extra": "allow"}


class GGCheckoutWebhookPayload(BaseModel):
    """
    Payload enviado pelo GG Checkout a cada evento de pagamento.

    Eventos:
    - payment.created    → pagamento criado (pendente)
    - payment.paid       → pagamento confirmado → libera acesso
    - payment.refunded   → reembolso → revoga acesso
    - payment.chargeback → chargeback → revoga acesso
    - payment.expired    → expirado → atualiza status
    """
    event: str
    payment: GGCheckoutPaymentData
    product: GGCheckoutProductData | None = None

    model_config = {"extra": "allow"}
