package com.acme.admin;

public class AuditEvents {
    @KafkaListener(topics = "inventory-updates")
    public void onInventory(String message) {
    }

    @RabbitListener(queues = "${rabbit.audit.queue}")
    public void onAudit(String message) {
        kafkaTemplate.send("price-changes", message);
    }
}
