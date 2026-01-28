package com.example.orderapi.schema.external;

import java.util.Map;

/**
 * Stripe webhook payload structure.
 *
 * We receive these webhooks for payment status updates.
 * Stripe versioning: STRIPE_WEBHOOK_VERSION in AppConfig.
 */
public class StripeWebhookEvent {
    private final String id;
    private final String type;  // payment_intent.succeeded, payment_intent.payment_failed, etc.
    private final long created;
    private final Map<String, Object> data;  // Contains the relevant object (PaymentIntent, Charge, etc.)
    private final boolean livemode;
    private final String apiVersion;

    public StripeWebhookEvent(String id, String type, long created,
                              Map<String, Object> data, boolean livemode, String apiVersion) {
        this.id = id;
        this.type = type;
        this.created = created;
        this.data = data;
        this.livemode = livemode;
        this.apiVersion = apiVersion;
    }

    public String getId() { return id; }
    public String getType() { return type; }
    public long getCreated() { return created; }
    public Map<String, Object> getData() { return data; }
    public boolean isLivemode() { return livemode; }
    public String getApiVersion() { return apiVersion; }
}
