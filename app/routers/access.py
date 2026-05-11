from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.customer import Customer
from app.models.payment import Payment
from app.schemas.payment import AccessStatusResponse, PaymentResponse

router = APIRouter(prefix="/access", tags=["Acesso"])


@router.get("/check", response_model=AccessStatusResponse)
async def check_access(email: str, db: AsyncSession = Depends(get_db)):
    """
    Verifica se um cliente tem acesso ao sistema pelo e-mail.

    Use este endpoint para consultar, no seu sistema, se o cliente
    já realizou o pagamento e tem acesso liberado.
    """
    result = await db.execute(select(Customer).where(Customer.email == email))
    customer = result.scalar_one_or_none()

    if not customer:
        return AccessStatusResponse(
            email=email,
            has_access=False,
            message="Cliente não encontrado. Nenhum pagamento registrado para este e-mail.",
        )

    if customer.has_access:
        message = "Acesso liberado. Pagamento confirmado."
    else:
        message = "Acesso pendente. Pagamento não confirmado ou reembolsado."

    return AccessStatusResponse(
        email=customer.email,
        has_access=customer.has_access,
        access_granted_at=customer.access_granted_at,
        message=message,
    )


@router.get("/payments", response_model=list[PaymentResponse])
async def list_payments_by_email(email: str, db: AsyncSession = Depends(get_db)):
    """
    Lista todos os pagamentos registrados para um e-mail.
    """
    result = await db.execute(select(Customer).where(Customer.email == email))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nenhum registro encontrado para este e-mail.",
        )

    pay_result = await db.execute(
        select(Payment)
        .where(Payment.customer_id == customer.id)
        .order_by(Payment.created_at.desc())
    )
    return pay_result.scalars().all()
