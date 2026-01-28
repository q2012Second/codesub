package com.example.orderapi.service;

/**
 * Raised when order validation fails.
 */
public class OrderValidationException extends RuntimeException {
    public OrderValidationException(String message) {
        super(message);
    }
}
