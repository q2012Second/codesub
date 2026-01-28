package com.example.orderapi.schema.api;

import java.time.Instant;
import java.util.List;

/**
 * POST /api/orders response body.
 *
 * Returned after successful order creation.
 * Contains payment client_secret for Stripe checkout.
 */
public class CreateOrderResponse {
    private final String orderId;
    private final List<OrderItemResponse> items;
    private final PricingBreakdown pricing;
    private final String stripeClientSecret;
    private final Instant createdAt;

    public CreateOrderResponse(String orderId, List<OrderItemResponse> items,
                               PricingBreakdown pricing, String stripeClientSecret,
                               Instant createdAt) {
        this.orderId = orderId;
        this.items = items;
        this.pricing = pricing;
        this.stripeClientSecret = stripeClientSecret;
        this.createdAt = createdAt;
    }

    public String getOrderId() { return orderId; }
    public List<OrderItemResponse> getItems() { return items; }
    public PricingBreakdown getPricing() { return pricing; }
    public String getStripeClientSecret() { return stripeClientSecret; }
    public Instant getCreatedAt() { return createdAt; }
}
