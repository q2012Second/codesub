package com.example.orderapi.model;

import java.io.Serializable;
import java.time.Instant;

/**
 * Customer preferences entity - demonstrates JPA-style field annotations.
 *
 * This entity shows how codesub can track changes to annotation properties
 * like @Column(length=..., nullable=...) which affect database schema.
 */
public class CustomerPreference implements Serializable {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "ID")
    private Long id;

    @Column(name = "CUSTOMER_ID", nullable = false, length = 36)
    private String customerId;

    @Column(name = "PREFERENCE_KEY", nullable = false, length = 100)
    private String preferenceKey;

    @Column(name = "PREFERENCE_VALUE", nullable = true, length = 500)
    private String preferenceValue;

    @Column(name = "CREATED_AT", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "UPDATED_AT", nullable = false)
    private Instant updatedAt;

    public CustomerPreference() {
        this.createdAt = Instant.now();
        this.updatedAt = Instant.now();
    }

    public CustomerPreference(String customerId, String preferenceKey, String preferenceValue) {
        this();
        this.customerId = customerId;
        this.preferenceKey = preferenceKey;
        this.preferenceValue = preferenceValue;
    }

    // Getters
    public Long getId() { return id; }
    public String getCustomerId() { return customerId; }
    public String getPreferenceKey() { return preferenceKey; }
    public String getPreferenceValue() { return preferenceValue; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }

    // Setters
    public void setPreferenceValue(String preferenceValue) {
        this.preferenceValue = preferenceValue;
        this.updatedAt = Instant.now();
    }
}
