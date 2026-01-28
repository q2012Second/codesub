package com.example.orderapi.model;

import java.math.BigDecimal;

/**
 * Catalog item.
 */
public class Product {
    private final String id;
    private final String name;
    private final BigDecimal price;
    private int stock;

    public Product(String id, String name, BigDecimal price) {
        this(id, name, price, 0);
    }

    public Product(String id, String name, BigDecimal price, int stock) {
        this.id = id;
        this.name = name;
        this.price = price;
        this.stock = stock;
    }

    public String getId() { return id; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
    public int getStock() { return stock; }

    public boolean isAvailable(int quantity) {
        return stock >= quantity;
    }

    public void setStock(int stock) {
        this.stock = stock;
    }
}
