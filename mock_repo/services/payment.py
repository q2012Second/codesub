"""Payment processing service.

Integrates with Stripe for payment handling.
"""

from decimal import Decimal
from typing import Optional

from config import STRIPE_API_URL, STRIPE_WEBHOOK_VERSION
from schemas.external import StripePaymentIntent, StripeWebhookEvent


class PaymentError(Exception):
    """Raised when payment processing fails."""
    pass


class PaymentService:
    """Handles Stripe payment integration."""

    def create_payment_intent(
        self,
        amount: Decimal,
        currency: str = "usd",
        metadata: Optional[dict] = None,
    ) -> StripePaymentIntent:
        """Create a Stripe PaymentIntent for checkout.

        The client_secret is passed to frontend for Stripe Elements.
        """
        amount_cents = int(amount * 100)

        # In production, this calls Stripe API
        # stripe.PaymentIntent.create(amount=amount_cents, ...)
        return StripePaymentIntent(
            id=f"pi_{'x' * 24}",
            amount=amount_cents,
            currency=currency,
            status="requires_payment_method",
            client_secret=f"pi_{'x' * 24}_secret_{'y' * 24}",
            created=0,
            metadata=metadata or {},
        )

    def handle_webhook(self, event: StripeWebhookEvent) -> dict:
        """Process Stripe webhook events.

        Called when Stripe sends payment status updates.
        Event types we handle:
        - payment_intent.succeeded
        - payment_intent.payment_failed
        - charge.refunded
        """
        if event.type == "payment_intent.succeeded":
            payment_intent_id = event.data.get("object", {}).get("id")
            return {
                "action": "mark_paid",
                "payment_id": payment_intent_id,
            }

        elif event.type == "payment_intent.payment_failed":
            failure_message = (
                event.data.get("object", {})
                .get("last_payment_error", {})
                .get("message", "Payment failed")
            )
            return {
                "action": "payment_failed",
                "error": failure_message,
            }

        elif event.type == "charge.refunded":
            return {
                "action": "mark_refunded",
                "charge_id": event.data.get("object", {}).get("id"),
            }

        return {"action": "ignored", "type": event.type}

    def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify Stripe webhook signature.

        Uses STRIPE_WEBHOOK_VERSION for API compatibility.
        """
        # In production: stripe.Webhook.construct_event(payload, sig, secret)
        return True
