package com.acme.orders;

import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(
    name = "pricing",
    url = "${pricing.url}"
)
public interface PricingClient {}
