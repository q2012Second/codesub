package com.example.orderapi.model;

import java.time.Instant;

/**
 * Customer account.
 */
public class User {
    private final String id;
    private final String email;
    private final String name;
    private final String region;
    private final Instant createdAt;

    public User(String id, String email, String name) {
        this(id, email, name, "US-CA");
    }

    public User(String id, String email, String name, String region) {
        this.id = id;
        this.email = email;
        this.name = name;
        this.region = region;
        this.createdAt = Instant.now();
    }

    public String getId() { return id; }
    public String getEmail() { return email; }
    public String getName() { return name; }
    public String getRegion() { return region; }
    public Instant getCreatedAt() { return createdAt; }
}
