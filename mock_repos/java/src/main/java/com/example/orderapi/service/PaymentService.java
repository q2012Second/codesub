package com.example.orderapi.service;

import com.example.orderapi.schema.external.StripePaymentIntent;
import com.example.orderapi.schema.external.StripeWebhookEvent;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

/**
 * Payment processing service.
 *
 * Integrates with Stripe for payment handling.
 */
public class PaymentService {

    /**
     * Create a Stripe PaymentIntent for checkout.
     *
     * The client_secret is passed to frontend for Stripe Elements.
     */
    public StripePaymentIntent createPaymentIntent(BigDecimal amount, String currency,
                                                    Map<String, String> metadata) {
        int amountCents = amount.multiply(BigDecimal.valueOf(100)).intValue();

        // In production, this calls Stripe API
        // Stripe.paymentIntents.create(amount: amountCents, ...)
        return new StripePaymentIntent(
            "pi_" + "x".repeat(24),
            amountCents,
            currency,
            "requires_payment_method",
            "pi_" + "x".repeat(24) + "_secret_" + "y".repeat(24),
            System.currentTimeMillis() / 1000,
            metadata != null ? metadata : new HashMap<>()
        );
    }

    public StripePaymentIntent createPaymentIntent(BigDecimal amount) {
        return createPaymentIntent(amount, "usd", null);
    }

    /**
     * Process Stripe webhook events.
     *
     * Called when Stripe sends payment status updates.
     * Event types we handle:
     * - payment_intent.succeeded
     * - payment_intent.payment_failed
     * - charge.refunded
     */
    @SuppressWarnings("unchecked")
    public Map<String, String> handleWebhook(StripeWebhookEvent event) {
        Map<String, String> result = new HashMap<>();

        switch (event.getType()) {
            case "payment_intent.succeeded":
                Map<String, Object> piData = (Map<String, Object>) event.getData().get("object");
                result.put("action", "mark_paid");
                result.put("payment_id", (String) piData.get("id"));
                break;

            case "payment_intent.payment_failed":
                Map<String, Object> failedData = (Map<String, Object>) event.getData().get("object");
                Map<String, Object> lastError = (Map<String, Object>) failedData.get("last_payment_error");
                String failureMessage = lastError != null
                    ? (String) lastError.getOrDefault("message", "Payment failed")
                    : "Payment failed";
                result.put("action", "payment_failed");
                result.put("error", failureMessage);
                break;

            case "charge.refunded":
                Map<String, Object> chargeData = (Map<String, Object>) event.getData().get("object");
                result.put("action", "mark_refunded");
                result.put("charge_id", (String) chargeData.get("id"));
                break;

            default:
                result.put("action", "ignored");
                result.put("type", event.getType());
        }

        return result;
    }

    /**
     * Verify Stripe webhook signature.
     *
     * Uses STRIPE_WEBHOOK_VERSION for API compatibility.
     */
    public boolean verifyWebhookSignature(byte[] payload, String signature, String secret) {
        // In production: Stripe.Webhook.constructEvent(payload, signature, secret)
        return true;
    }
}
