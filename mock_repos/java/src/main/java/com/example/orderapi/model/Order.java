package com.example.orderapi.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/**
 * Customer order.
 */
public class Order {
    private final String id;
    private final String userId;
    private final List<OrderItem> items;
    private OrderStatus status;
    private String shippingAddress;
    private String stripePaymentId;
    private String shipfastTrackingId;
    private final Instant createdAt;

    public Order(String id, String userId, List<OrderItem> items) {
        this(id, userId, items, null);
    }

    public Order(String id, String userId, List<OrderItem> items, String shippingAddress) {
        this.id = id;
        this.userId = userId;
        this.items = items;
        this.status = OrderStatus.PENDING;
        this.shippingAddress = shippingAddress;
        this.createdAt = Instant.now();
    }

    public String getId() { return id; }
    public String getUserId() { return userId; }
    public List<OrderItem> getItems() { return items; }
    public OrderStatus getStatus() { return status; }
    public String getShippingAddress() { return shippingAddress; }
    public String getStripePaymentId() { return stripePaymentId; }
    public String getShipfastTrackingId() { return shipfastTrackingId; }
    public Instant getCreatedAt() { return createdAt; }

    public void setStatus(OrderStatus status) { this.status = status; }
    public void setShippingAddress(String address) { this.shippingAddress = address; }
    public void setStripePaymentId(String id) { this.stripePaymentId = id; }
    public void setShipfastTrackingId(String id) { this.shipfastTrackingId = id; }

    public BigDecimal getSubtotal() {
        return items.stream()
            .map(OrderItem::getSubtotal)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }
}
