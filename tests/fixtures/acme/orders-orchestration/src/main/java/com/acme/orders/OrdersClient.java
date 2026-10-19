package com.acme.orders;

import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(name = "orders-service")
public interface OrdersClient {}
