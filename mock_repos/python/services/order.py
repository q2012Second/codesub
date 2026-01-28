"""Order processing service.

Contains critical business logic for order creation and pricing.
"""

from decimal import Decimal
from typing import Optional

from config import (
    MIN_ORDER_AMOUNT,
    MAX_ORDER_ITEMS,
    FREE_SHIPPING_THRESHOLD,
    TAX_RATES,
)
from models import Order, OrderItem, User, Product, OrderStatus
from schemas.api import PricingBreakdown


class OrderValidationError(Exception):
    """Raised when order validation fails."""
    pass


class OrderService:
    """Handles order creation and management."""

    SHIPPING_RATE = Decimal("5.99")

    def validate_order(self, items: list[OrderItem], user: User) -> None:
        """Validate order before creation.

        Raises OrderValidationError if validation fails.
        """
        if not items:
            raise OrderValidationError("Order must have at least one item")

        if len(items) > MAX_ORDER_ITEMS:
            raise OrderValidationError(
                f"Order cannot exceed {MAX_ORDER_ITEMS} items"
            )

        subtotal = sum(item.subtotal for item in items)
        if subtotal < Decimal(str(MIN_ORDER_AMOUNT)):
            raise OrderValidationError(
                f"Order minimum is ${MIN_ORDER_AMOUNT:.2f}"
            )

    def calculate_pricing(
        self,
        items: list[OrderItem],
        user: User,
    ) -> PricingBreakdown:
        """Calculate order totals including tax and shipping.

        This is critical business logic - changes affect revenue.
        """
        subtotal = sum(item.subtotal for item in items)

        # Tax calculation based on user region
        tax_rate = TAX_RATES.get(user.region, TAX_RATES["DEFAULT"])
        tax = subtotal * Decimal(str(tax_rate))

        # Free shipping over threshold
        if subtotal >= Decimal(str(FREE_SHIPPING_THRESHOLD)):
            shipping = Decimal("0.00")
        else:
            shipping = self.SHIPPING_RATE

        total = subtotal + tax + shipping

        return PricingBreakdown(
            subtotal=subtotal.quantize(Decimal("0.01")),
            tax=tax.quantize(Decimal("0.01")),
            shipping=shipping.quantize(Decimal("0.01")),
            total=total.quantize(Decimal("0.01")),
        )

    def create_order(
        self,
        order_id: str,
        user: User,
        items: list[OrderItem],
        shipping_address: str,
    ) -> Order:
        """Create a new order after validation."""
        self.validate_order(items, user)

        return Order(
            id=order_id,
            user_id=user.id,
            items=items,
            shipping_address=shipping_address,
            status=OrderStatus.PENDING,
        )

    def mark_paid(self, order: Order, payment_id: str) -> Order:
        """Mark order as paid after successful payment."""
        order.status = OrderStatus.PAID
        order.stripe_payment_id = payment_id
        return order

    def mark_shipped(self, order: Order, tracking_id: str) -> Order:
        """Mark order as shipped with tracking info."""
        order.status = OrderStatus.SHIPPED
        order.shipfast_tracking_id = tracking_id
        return order
