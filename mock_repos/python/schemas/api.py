"""Public API request/response schemas.

These are our API contracts with frontend clients and partners.
Changes here are BREAKING CHANGES that affect API consumers.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional


# =============================================================================
# Order API Schemas
# =============================================================================

@dataclass
class OrderItemRequest:
    """Item in a create order request."""
    product_id: str
    quantity: int


@dataclass
class CreateOrderRequest:
    """POST /api/orders request body.

    Frontend sends this to create a new order.
    """
    items: list[OrderItemRequest]
    shipping_address: str


@dataclass
class OrderItemResponse:
    """Item in order response."""
    product_id: str
    product_name: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


@dataclass
class PricingBreakdown:
    """Price calculation details returned to client."""
    subtotal: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal


@dataclass
class CreateOrderResponse:
    """POST /api/orders response body.

    Returned after successful order creation.
    Contains payment client_secret for Stripe checkout.
    """
    order_id: str
    items: list[OrderItemResponse]
    pricing: PricingBreakdown
    stripe_client_secret: str
    created_at: datetime


@dataclass
class OrderResponse:
    """GET /api/orders/{id} response body.

    Full order details for order status page.
    """
    order_id: str
    status: str
    items: list[OrderItemResponse]
    pricing: PricingBreakdown
    shipping_address: str
    tracking_number: Optional[str]
    tracking_url: Optional[str]
    created_at: datetime
    updated_at: datetime


# =============================================================================
# Common Response Schemas
# =============================================================================

@dataclass
class ErrorResponse:
    """Standard error response format.

    All API errors follow this structure.
    """
    error_code: str
    message: str
    details: Optional[dict] = None


@dataclass
class PaginatedResponse:
    """Wrapper for paginated list responses."""
    items: list
    total: int
    page: int
    per_page: int
    has_next: bool
