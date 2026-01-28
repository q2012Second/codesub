package com.example.orderapi.schema.api;

import java.math.BigDecimal;

/**
 * Price calculation details returned to client.
 *
 * Public API contract - changes here affect frontend/mobile clients.
 */
public class PricingBreakdown {
    private final BigDecimal subtotal;
    private final BigDecimal tax;
    private final BigDecimal shipping;
    private final BigDecimal total;

    public PricingBreakdown(BigDecimal subtotal, BigDecimal tax,
                            BigDecimal shipping, BigDecimal total) {
        this.subtotal = subtotal;
        this.tax = tax;
        this.shipping = shipping;
        this.total = total;
    }

    public BigDecimal getSubtotal() { return subtotal; }
    public BigDecimal getTax() { return tax; }
    public BigDecimal getShipping() { return shipping; }
    public BigDecimal getTotal() { return total; }
}
