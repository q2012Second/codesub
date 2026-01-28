"""Schemas for external service responses.

These structures match the API contracts of external providers.
Changes here indicate the provider changed their API - requires code updates.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


# =============================================================================
# Stripe Payment Provider (https://stripe.com/docs/api)
# =============================================================================

@dataclass
class StripePaymentIntent:
    """Response from Stripe when creating a payment.

    Stripe API reference: POST /v1/payment_intents
    If Stripe changes this structure, our payment processing breaks.
    """
    id: str
    amount: int  # in cents
    currency: str
    status: str  # requires_payment_method, requires_confirmation, succeeded, etc.
    client_secret: str
    created: int  # Unix timestamp
    metadata: dict


@dataclass
class StripeCharge:
    """Charge object within a PaymentIntent."""
    id: str
    amount: int
    amount_refunded: int
    paid: bool
    refunded: bool
    failure_code: Optional[str]
    failure_message: Optional[str]


@dataclass
class StripeWebhookEvent:
    """Stripe webhook payload structure.

    We receive these webhooks for payment status updates.
    Stripe versioning: STRIPE_WEBHOOK_VERSION in config.py
    """
    id: str
    type: str  # payment_intent.succeeded, payment_intent.payment_failed, etc.
    created: int
    data: dict  # Contains the relevant object (PaymentIntent, Charge, etc.)
    livemode: bool
    api_version: str


# =============================================================================
# ShipFast Shipping Provider
# =============================================================================

@dataclass
class ShipFastAddress:
    """Address format expected by ShipFast API."""
    name: str
    street: str
    city: str
    state: str
    postal_code: str
    country: str = "US"


@dataclass
class ShipFastShipment:
    """Response from ShipFast when creating a shipment.

    ShipFast API: POST /v3/shipments
    """
    shipment_id: str
    tracking_number: str
    carrier: str
    estimated_delivery: datetime
    label_url: str
    status: str  # pending, in_transit, delivered, exception


@dataclass
class ShipFastTrackingEvent:
    """Tracking update from ShipFast webhook.

    Received via webhook when package status changes.
    """
    shipment_id: str
    tracking_number: str
    status: str
    location: str
    timestamp: datetime
    details: Optional[str] = None
