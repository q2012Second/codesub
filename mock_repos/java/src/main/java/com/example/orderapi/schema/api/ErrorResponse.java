package com.example.orderapi.schema.api;

import java.util.Map;

/**
 * Standard error response format.
 *
 * All API errors follow this structure.
 */
public class ErrorResponse {
    private final String errorCode;
    private final String message;
    private final Map<String, Object> details;

    public ErrorResponse(String errorCode, String message) {
        this(errorCode, message, null);
    }

    public ErrorResponse(String errorCode, String message, Map<String, Object> details) {
        this.errorCode = errorCode;
        this.message = message;
        this.details = details;
    }

    public String getErrorCode() { return errorCode; }
    public String getMessage() { return message; }
    public Map<String, Object> getDetails() { return details; }
}
