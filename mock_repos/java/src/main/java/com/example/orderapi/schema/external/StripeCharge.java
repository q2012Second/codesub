package com.example.orderapi.schema.external;

/**
 * Charge object within a PaymentIntent.
 */
public class StripeCharge {
    private final String id;
    private final int amount;
    private final int amountRefunded;
    private final boolean paid;
    private final boolean refunded;
    private final String failureCode;
    private final String failureMessage;

    public StripeCharge(String id, int amount, int amountRefunded, boolean paid,
                        boolean refunded, String failureCode, String failureMessage) {
        this.id = id;
        this.amount = amount;
        this.amountRefunded = amountRefunded;
        this.paid = paid;
        this.refunded = refunded;
        this.failureCode = failureCode;
        this.failureMessage = failureMessage;
    }

    public String getId() { return id; }
    public int getAmount() { return amount; }
    public int getAmountRefunded() { return amountRefunded; }
    public boolean isPaid() { return paid; }
    public boolean isRefunded() { return refunded; }
    public String getFailureCode() { return failureCode; }
    public String getFailureMessage() { return failureMessage; }
}
