package com.acme.admin;

import org.springframework.cloud.openfeign.FeignClient;

@FeignClient(name = "pricing-svc", url = "${pricing.url}")
public interface PricingClient {}
