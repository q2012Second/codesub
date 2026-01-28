package com.example.orderapi.schema.api;

import java.time.Instant;
import java.util.List;

/**
 * GET /api/orders/{id} response body.
 *
 * Full order details for order status page.
 */
public class OrderResponse {
    private final String orderId;
    private final String status;
    private final List<OrderItemResponse> items;
    private final PricingBreakdown pricing;
    private final String shippingAddress;
    private final String trackingNumber;
    private final String trackingUrl;
    private final Instant createdAt;
    private final Instant updatedAt;

    public OrderResponse(String orderId, String status, List<OrderItemResponse> items,
                         PricingBreakdown pricing, String shippingAddress,
                         String trackingNumber, String trackingUrl,
                         Instant createdAt, Instant updatedAt) {
        this.orderId = orderId;
        this.status = status;
        this.items = items;
        this.pricing = pricing;
        this.shippingAddress = shippingAddress;
        this.trackingNumber = trackingNumber;
        this.trackingUrl = trackingUrl;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
    }

    public String getOrderId() { return orderId; }
    public String getStatus() { return status; }
    public List<OrderItemResponse> getItems() { return items; }
    public PricingBreakdown getPricing() { return pricing; }
    public String getShippingAddress() { return shippingAddress; }
    public String getTrackingNumber() { return trackingNumber; }
    public String getTrackingUrl() { return trackingUrl; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
