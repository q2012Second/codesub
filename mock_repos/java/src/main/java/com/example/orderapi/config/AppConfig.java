package com.example.orderapi.config;

import java.math.BigDecimal;
import java.util.Map;

/**
 * Application configuration constants.
 * External service URLs and business settings.
 */
public final class AppConfig {
    private AppConfig() {} // Prevent instantiation

    // API versioning - tracked by clients
    public static final String API_VERSION = "v2";

    // Stripe payment integration
    public static final String STRIPE_API_URL = "https://api.stripe.com/v1";
    public static final String STRIPE_WEBHOOK_VERSION = "2024-01-01";

    // ShipFast shipping provider
    public static final String SHIPFAST_API_URL = "https://api.shipfast.io/v3";
    public static final String SHIPFAST_WEBHOOK_SECRET = "whsec_xxxxx";

    // Order processing
    public static final BigDecimal MIN_ORDER_AMOUNT = new BigDecimal("10.00");
    public static final int MAX_ORDER_ITEMS = 50;
    public static final BigDecimal FREE_SHIPPING_THRESHOLD = new BigDecimal("100.00");

    // Tax rates by region (decimal)
    public static final Map<String, BigDecimal> TAX_RATES = Map.of(
        "US-CA", new BigDecimal("0.0725"),
        "US-NY", new BigDecimal("0.08"),
        "US-TX", new BigDecimal("0.0625"),
        "EU", new BigDecimal("0.20"),
        "DEFAULT", BigDecimal.ZERO
    );
}
