package com.example.orderapi.schema.api;

/**
 * Item in a create order request.
 */
public class OrderItemRequest {
    private final String productId;
    private final int quantity;

    public OrderItemRequest(String productId, int quantity) {
        this.productId = productId;
        this.quantity = quantity;
    }

    public String getProductId() { return productId; }
    public int getQuantity() { return quantity; }
}
