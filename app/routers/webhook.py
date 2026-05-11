import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.customer import Customer
from app.models.payment import Payment, WebhookEvent
from app.schemas.payment import GGCheckoutWebhookPayload
from app.services.ggcheckout import ggcheckout_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

ACCESS_GRANT_EVENTS = {"payment.paid"}
ACCESS_REVOKE_EVENTS = {"payment.refunded", "payment.chargeback"}


@router.post("/ggcheckout", status_code=status.HTTP_200_OK)
async def ggcheckout_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Receptor de webhooks do GG Checkout.

    Após o cliente pagar no checkout do GG Checkout (com gateway AbacatePay),
    o GG Checkout envia este evento. O serviço então registra o cliente
    e libera (ou revoga) o acesso automaticamente.

    Segurança: assinatura HMAC-SHA256 no header X-Webhook-Signature.
    """
    raw_body = await request.body()

    # ── Validar assinatura HMAC ───────────────────────────────────────────────
    signature = request.headers.get("X-Webhook-Signature", "")
    if not ggcheckout_service.verify_webhook_signature(raw_body, signature):
        logger.warning(
            "Webhook com assinatura inválida | IP=%s",
            request.client.host if request.client else "?",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Assinatura do webhook inválida",
        )

    # ── Parse do payload ──────────────────────────────────────────────────────
    try:
        payload = GGCheckoutWebhookPayload.model_validate_json(raw_body)
    except Exception as exc:
        logger.error("Payload inválido: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Payload inválido",
        ) from exc

    event_type = payload.event
    payment_id = payload.payment.id

    logger.info("Evento recebido: %s | payment=%s", event_type, payment_id)

    # ── Idempotência ──────────────────────────────────────────────────────────
    idempotency_key = f"{payment_id}:{event_type}"
    existing = await db.execute(
        select(WebhookEvent).where(WebhookEvent.idempotency_key == idempotency_key)
    )
    if existing.scalar_one_or_none():
        logger.info("Evento duplicado ignorado: %s", idempotency_key)
        return {"status": "already_processed"}

    # ── Registrar evento ──────────────────────────────────────────────────────
    webhook_event = WebhookEvent(
        idempotency_key=idempotency_key,
        event_type=event_type,
        payload=payload.model_dump(),
        processed=False,
    )
    db.add(webhook_event)
    await db.flush()

    # ── Processar ─────────────────────────────────────────────────────────────
    try:
        if event_type in ACCESS_GRANT_EVENTS:
            await _grant_access(payload, db)

        elif event_type in ACCESS_REVOKE_EVENTS:
            await _revoke_access(payload, event_type, db)

        elif event_type == "payment.expired":
            await _mark_expired(payload, db)

        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(timezone.utc)

    except Exception as exc:
        webhook_event.processing_error = str(exc)
        logger.exception("Erro ao processar evento %s: %s", event_type, exc)

    return {"status": "ok"}


# ── Handlers ──────────────────────────────────────────────────────────────────

async def _grant_access(payload: GGCheckoutWebhookPayload, db: AsyncSession) -> None:
    """
    Pagamento confirmado → cria ou atualiza o cliente e libera o acesso.
    """
    p = payload.payment
    customer_data = p.customer
    now = datetime.now(timezone.utc)

    email = customer_data.email if customer_data else None
    if not email:
        logger.warning("payment.paid sem e-mail do cliente | payment=%s", p.id)
        return

    # Buscar ou criar cliente
    result = await db.execute(select(Customer).where(Customer.email == email))
    customer = result.scalar_one_or_none()

    if not customer:
        customer = Customer(
            email=email,
            name=customer_data.name if customer_data else None,
            document=customer_data.document if customer_data else None,
            phone=customer_data.phone if customer_data else None,
        )
        db.add(customer)
        await db.flush()
        logger.info("Novo cliente criado: %s", email)
    else:
        # Atualizar dados caso tenham mudado
        if customer_data:
            customer.name = customer_data.name or customer.name
            customer.document = customer_data.document or customer.document
            customer.phone = customer_data.phone or customer.phone

    # Liberar acesso
    customer.has_access = True
    customer.access_granted_at = now
    customer.access_revoked_at = None

    # Registrar ou atualizar pagamento
    pay_result = await db.execute(
        select(Payment).where(Payment.ggcheckout_payment_id == p.id)
    )
    payment = pay_result.scalar_one_or_none()

    if not payment:
        payment = Payment(
            customer_id=customer.id,
            ggcheckout_payment_id=p.id,
            ggcheckout_product_id=payload.product.id if payload.product else None,
            ggcheckout_product_title=payload.product.title if payload.product else None,
            amount=p.amount,
            status="PAID",
            payment_method=p.method,
            raw_payload=payload.model_dump(),
            paid_at=now,
        )
        db.add(payment)
    else:
        payment.status = "PAID"
        payment.paid_at = now
        payment.payment_method = p.method
        payment.amount = p.amount

    logger.info("Acesso LIBERADO | email=%s | payment=%s", email, p.id)


async def _revoke_access(
    payload: GGCheckoutWebhookPayload,
    event_type: str,
    db: AsyncSession,
) -> None:
    """
    Reembolso ou chargeback → revoga o acesso do cliente.
    """
    p = payload.payment
    now = datetime.now(timezone.utc)
    new_status = "REFUNDED" if event_type == "payment.refunded" else "CHARGEBACK"

    # Atualizar pagamento
    pay_result = await db.execute(
        select(Payment).where(Payment.ggcheckout_payment_id == p.id)
    )
    payment = pay_result.scalar_one_or_none()
    if payment:
        payment.status = new_status
        payment.refunded_at = now

        # Revogar acesso do cliente
        cust_result = await db.execute(
            select(Customer).where(Customer.id == payment.customer_id)
        )
        customer = cust_result.scalar_one_or_none()
        if customer:
            customer.has_access = False
            customer.access_revoked_at = now
            logger.info(
                "Acesso REVOGADO | email=%s | evento=%s | payment=%s",
                customer.email, event_type, p.id,
            )


async def _mark_expired(payload: GGCheckoutWebhookPayload, db: AsyncSession) -> None:
    """Pagamento expirado → atualiza status."""
    p = payload.payment
    pay_result = await db.execute(
        select(Payment).where(Payment.ggcheckout_payment_id == p.id)
    )
    payment = pay_result.scalar_one_or_none()
    if payment:
        payment.status = "EXPIRED"
        logger.info("Pagamento EXPIRADO | payment=%s", p.id)
