package com.example.orderapi.schema.external;

import java.time.Instant;

/**
 * Tracking update from ShipFast webhook.
 *
 * Received via webhook when package status changes.
 */
public class ShipFastTrackingEvent {
    private final String shipmentId;
    private final String trackingNumber;
    private final String status;
    private final String location;
    private final Instant timestamp;
    private final String details;

    public ShipFastTrackingEvent(String shipmentId, String trackingNumber, String status,
                                  String location, Instant timestamp) {
        this(shipmentId, trackingNumber, status, location, timestamp, null);
    }

    public ShipFastTrackingEvent(String shipmentId, String trackingNumber, String status,
                                  String location, Instant timestamp, String details) {
        this.shipmentId = shipmentId;
        this.trackingNumber = trackingNumber;
        this.status = status;
        this.location = location;
        this.timestamp = timestamp;
        this.details = details;
    }

    public String getShipmentId() { return shipmentId; }
    public String getTrackingNumber() { return trackingNumber; }
    public String getStatus() { return status; }
    public String getLocation() { return location; }
    public Instant getTimestamp() { return timestamp; }
    public String getDetails() { return details; }
}
