package com.example.orderapi.schema.external;

/**
 * Address format expected by ShipFast API.
 */
public class ShipFastAddress {
    private final String name;
    private final String street;
    private final String city;
    private final String state;
    private final String postalCode;
    private final String country;

    public ShipFastAddress(String name, String street, String city,
                           String state, String postalCode) {
        this(name, street, city, state, postalCode, "US");
    }

    public ShipFastAddress(String name, String street, String city,
                           String state, String postalCode, String country) {
        this.name = name;
        this.street = street;
        this.city = city;
        this.state = state;
        this.postalCode = postalCode;
        this.country = country;
    }

    public String getName() { return name; }
    public String getStreet() { return street; }
    public String getCity() { return city; }
    public String getState() { return state; }
    public String getPostalCode() { return postalCode; }
    public String getCountry() { return country; }
}
