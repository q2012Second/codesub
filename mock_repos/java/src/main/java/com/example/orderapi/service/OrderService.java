package com.example.orderapi.service;

import com.example.orderapi.config.AppConfig;
import com.example.orderapi.model.Order;
import com.example.orderapi.model.OrderItem;
import com.example.orderapi.model.OrderStatus;
import com.example.orderapi.model.User;
import com.example.orderapi.schema.api.PricingBreakdown;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

/**
 * Order processing service.
 *
 * Contains critical business logic for order creation and pricing.
 */
public class OrderService {

    public static final BigDecimal SHIPPING_RATE = new BigDecimal("5.99");

    /**
     * Validate order before creation.
     *
     * @throws OrderValidationException if validation fails
     */
    public void validateOrder(List<OrderItem> items, User user) {
        if (items == null || items.isEmpty()) {
            throw new OrderValidationException("Order must have at least one item");
        }

        if (items.size() > AppConfig.MAX_ORDER_ITEMS) {
            throw new OrderValidationException(
                "Order cannot exceed " + AppConfig.MAX_ORDER_ITEMS + " items"
            );
        }

        BigDecimal subtotal = items.stream()
            .map(OrderItem::getSubtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        if (subtotal.compareTo(AppConfig.MIN_ORDER_AMOUNT) < 0) {
            throw new OrderValidationException(
                "Order minimum is $" + AppConfig.MIN_ORDER_AMOUNT
            );
        }
    }

    /**
     * Calculate order totals including tax and shipping.
     *
     * This is critical business logic - changes affect revenue.
     */
    public PricingBreakdown calculatePricing(List<OrderItem> items, User user) {
        BigDecimal subtotal = items.stream()
            .map(OrderItem::getSubtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        // Tax calculation based on user region
        BigDecimal taxRate = AppConfig.TAX_RATES.getOrDefault(
            user.getRegion(),
            AppConfig.TAX_RATES.get("DEFAULT")
        );
        BigDecimal tax = subtotal.multiply(taxRate);

        // Free shipping over threshold
        BigDecimal shipping;
        if (subtotal.compareTo(AppConfig.FREE_SHIPPING_THRESHOLD) >= 0) {
            shipping = BigDecimal.ZERO;
        } else {
            shipping = SHIPPING_RATE;
        }

        BigDecimal total = subtotal.add(tax).add(shipping);

        return new PricingBreakdown(
            subtotal.setScale(2, RoundingMode.HALF_UP),
            tax.setScale(2, RoundingMode.HALF_UP),
            shipping.setScale(2, RoundingMode.HALF_UP),
            total.setScale(2, RoundingMode.HALF_UP)
        );
    }

    /**
     * Create a new order after validation.
     */
    public Order createOrder(String orderId, User user, List<OrderItem> items,
                             String shippingAddress) {
        validateOrder(items, user);
        return new Order(orderId, user.getId(), items, shippingAddress);
    }

    /**
     * Mark order as paid after successful payment.
     */
    public Order markPaid(Order order, String paymentId) {
        order.setStatus(OrderStatus.PAID);
        order.setStripePaymentId(paymentId);
        return order;
    }

    /**
     * Mark order as shipped with tracking info.
     */
    public Order markShipped(Order order, String trackingId) {
        order.setStatus(OrderStatus.SHIPPED);
        order.setShipfastTrackingId(trackingId);
        return order;
    }
}
