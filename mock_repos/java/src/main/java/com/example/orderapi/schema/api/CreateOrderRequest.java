package com.example.orderapi.schema.api;

import java.util.List;

/**
 * POST /api/orders request body.
 *
 * Frontend sends this to create a new order.
 */
public class CreateOrderRequest {
    private final List<OrderItemRequest> items;
    private final String shippingAddress;

    public CreateOrderRequest(List<OrderItemRequest> items, String shippingAddress) {
        this.items = items;
        this.shippingAddress = shippingAddress;
    }

    public List<OrderItemRequest> getItems() { return items; }
    public String getShippingAddress() { return shippingAddress; }
}
