package com.acme.orders;

import org.springframework.beans.factory.annotation.Value;

public class InventoryClient {
    @Value("${inventory.base-url}")
    private String inventoryBaseUrl;
}
