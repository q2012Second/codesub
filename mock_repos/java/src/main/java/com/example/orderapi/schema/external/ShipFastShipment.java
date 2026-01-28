package com.example.orderapi.schema.external;

import java.time.Instant;

/**
 * Response from ShipFast when creating a shipment.
 *
 * ShipFast API: POST /v3/shipments
 */
public class ShipFastShipment {
    private final String shipmentId;
    private final String trackingNumber;
    private final String carrier;
    private final Instant estimatedDelivery;
    private final String labelUrl;
    private final String status;  // pending, in_transit, delivered, exception

    public ShipFastShipment(String shipmentId, String trackingNumber, String carrier,
                            Instant estimatedDelivery, String labelUrl, String status) {
        this.shipmentId = shipmentId;
        this.trackingNumber = trackingNumber;
        this.carrier = carrier;
        this.estimatedDelivery = estimatedDelivery;
        this.labelUrl = labelUrl;
        this.status = status;
    }

    public String getShipmentId() { return shipmentId; }
    public String getTrackingNumber() { return trackingNumber; }
    public String getCarrier() { return carrier; }
    public Instant getEstimatedDelivery() { return estimatedDelivery; }
    public String getLabelUrl() { return labelUrl; }
    public String getStatus() { return status; }
}
