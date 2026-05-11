import hashlib
import hmac
import httpx
from typing import Any

from app.config import get_settings

settings = get_settings()


class GGCheckoutService:
    """
    Serviço de integração com a API do GG Checkout.

    O GG Checkout é a plataforma de checkout. O AbacatePay é o gateway
    de pagamento configurado dentro do GG Checkout (via Gateway Tokens).
    Os webhooks vêm do GG Checkout com assinatura HMAC-SHA256 em hex.
    """

    def __init__(self) -> None:
        self.api_url = settings.GGCHECKOUT_API_URL
        self.api_key = settings.GGCHECKOUT_API_KEY
        self.webhook_secret = settings.GGCHECKOUT_WEBHOOK_SECRET

    def _get_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def get_checkout_url(self, checkout_id: str) -> str:
        """
        Retorna a URL pública de um checkout existente no GG Checkout.
        Use o slug/id do checkout configurado no painel.
        """
        return f"https://checkout.ggcheckout.com.br/{checkout_id}"

    async def create_payment_link(
        self,
        checkout_uid: str,
        customer_email: str | None = None,
        customer_name: str | None = None,
        external_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Cria um link de pagamento pré-preenchido via API do GG Checkout.
        O checkout_uid é o Firestore document ID do checkout no GG Checkout.
        """
        payload: dict[str, Any] = {}

        if customer_email:
            payload["customerEmail"] = customer_email
        if customer_name:
            payload["customerName"] = customer_name
        if external_id:
            payload["externalId"] = external_id

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.api_url}/checkouts/{checkout_uid}/payment-link",
                json=payload,
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        """Consulta os detalhes de um pagamento no GG Checkout."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.api_url}/payments/{payment_id}",
                headers=self._get_headers(),
            )
            response.raise_for_status()
            return response.json()

    def verify_webhook_signature(self, raw_body: bytes, signature_from_header: str) -> bool:
        """
        Valida a assinatura HMAC-SHA256 do GG Checkout.

        O header recebido é: X-Webhook-Signature: sha256=<hex>
        A verificação compara o HMAC calculado com o valor após 'sha256='.
        """
        if not signature_from_header:
            return False

        # Remove o prefixo "sha256=" se presente
        expected_prefix = "sha256="
        sig_value = (
            signature_from_header[len(expected_prefix):]
            if signature_from_header.startswith(expected_prefix)
            else signature_from_header
        )

        try:
            expected = hmac.new(
                self.webhook_secret.encode("utf-8"),
                raw_body,
                hashlib.sha256,
            ).hexdigest()

            return hmac.compare_digest(
                expected.encode("utf-8"),
                sig_value.encode("utf-8"),
            )
        except Exception:
            return False


ggcheckout_service = GGCheckoutService()
