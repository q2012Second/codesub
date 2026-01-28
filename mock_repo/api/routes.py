"""API endpoint handlers.

These endpoints form our public API contract.
"""

from typing import Optional
from schemas.api import (
    CreateOrderRequest,
    CreateOrderResponse,
    OrderResponse,
    ErrorResponse,
    PaginatedResponse,
)
from services import OrderService, PaymentService
from config import API_VERSION


# Simulated router (in production: FastAPI/Flask)
router = {}


def get(path: str):
    def decorator(func):
        router[("GET", path)] = func
        return func
    return decorator


def post(path: str):
    def decorator(func):
        router[("POST", path)] = func
        return func
    return decorator


# =============================================================================
# Order Endpoints
# =============================================================================

@post("/api/orders")
def create_order(request: CreateOrderRequest, user_id: str) -> CreateOrderResponse:
    """Create a new order.

    Returns order details with Stripe client_secret for payment.
    """
    order_service = OrderService()
    payment_service = PaymentService()

    # Create order (validation happens inside)
    # ... order creation logic ...

    # Return response matching CreateOrderResponse schema
    pass


@get("/api/orders/{order_id}")
def get_order(order_id: str, user_id: str) -> OrderResponse:
    """Get order details by ID.

    Returns full order info including tracking if shipped.
    """
    pass


@get("/api/orders")
def list_orders(
    user_id: str,
    page: int = 1,
    per_page: int = 20,
    status: Optional[str] = None,
) -> PaginatedResponse:
    """List user's orders with pagination."""
    pass


# =============================================================================
# Webhook Endpoints
# =============================================================================

@post("/webhooks/stripe")
def stripe_webhook(payload: bytes, signature: str) -> dict:
    """Handle Stripe payment webhooks.

    Processes payment_intent.succeeded, payment_failed, etc.
    """
    payment_service = PaymentService()
    # Verify signature and process event
    pass


@post("/webhooks/shipfast")
def shipfast_webhook(payload: dict) -> dict:
    """Handle ShipFast shipping webhooks.

    Updates order status when package is in_transit/delivered.
    """
    pass


# =============================================================================
# Health Check
# =============================================================================

@get("/health")
def health_check() -> dict:
    """Service health check endpoint."""
    return {
        "status": "healthy",
        "api_version": API_VERSION,
    }
