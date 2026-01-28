package com.example.orderapi.service;

/**
 * Raised when payment processing fails.
 */
public class PaymentException extends RuntimeException {
    public PaymentException(String message) {
        super(message);
    }
}
