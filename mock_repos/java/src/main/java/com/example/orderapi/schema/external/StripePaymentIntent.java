package com.example.orderapi.schema.external;

import java.util.Map;

/**
 * Response from Stripe when creating a payment.
 *
 * Stripe API reference: POST /v1/payment_intents
 * If Stripe changes this structure, our payment processing breaks.
 */
public class StripePaymentIntent {
    private final String id;
    private final int amount;  // in cents
    private final String currency;
    private final String status;  // requires_payment_method, requires_confirmation, succeeded, etc.
    private final String clientSecret;
    private final long created;  // Unix timestamp
    private final Map<String, String> metadata;

    public StripePaymentIntent(String id, int amount, String currency, String status,
                               String clientSecret, long created, Map<String, String> metadata) {
        this.id = id;
        this.amount = amount;
        this.currency = currency;
        this.status = status;
        this.clientSecret = clientSecret;
        this.created = created;
        this.metadata = metadata;
    }

    public String getId() { return id; }
    public int getAmount() { return amount; }
    public String getCurrency() { return currency; }
    public String getStatus() { return status; }
    public String getClientSecret() { return clientSecret; }
    public long getCreated() { return created; }
    public Map<String, String> getMetadata() { return metadata; }
}
