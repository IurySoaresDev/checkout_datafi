import uuid
from datetime import datetime
from sqlalchemy import String, Integer, ForeignKey, DateTime, Boolean, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Payment(Base):
    """Registro de pagamento recebido via webhook do GG Checkout."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ID do pagamento no GG Checkout (payment.id do webhook)
    ggcheckout_payment_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # ID e título do produto no GG Checkout
    ggcheckout_product_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ggcheckout_product_title: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Valor em centavos
    amount: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Status: PENDING | PAID | REFUNDED | EXPIRED | CHARGEBACK
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)

    # Método: card | card.paid | pix | pix.paid
    payment_method: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Payload completo do webhook para auditoria
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    customer = relationship("Customer", backref="payments", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Payment gg_id={self.ggcheckout_payment_id} status={self.status}>"
        )


class WebhookEvent(Base):
    """Log de todos os eventos recebidos do GG Checkout."""

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Chave de idempotência: payment_id + event_type
    idempotency_key: Mapped[str] = mapped_column(
        String(500), unique=True, nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
