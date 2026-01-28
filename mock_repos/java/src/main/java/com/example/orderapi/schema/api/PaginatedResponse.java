package com.example.orderapi.schema.api;

import java.util.List;

/**
 * Wrapper for paginated list responses.
 */
public class PaginatedResponse<T> {
    private final List<T> items;
    private final int total;
    private final int page;
    private final int perPage;
    private final boolean hasNext;

    public PaginatedResponse(List<T> items, int total, int page, int perPage, boolean hasNext) {
        this.items = items;
        this.total = total;
        this.page = page;
        this.perPage = perPage;
        this.hasNext = hasNext;
    }

    public List<T> getItems() { return items; }
    public int getTotal() { return total; }
    public int getPage() { return page; }
    public int getPerPage() { return perPage; }
    public boolean isHasNext() { return hasNext; }
}
