package com.acme.orders;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.jms.core.JmsTemplate;

public class OrderEventsPublisher {
    @Value("${aws.sqs.orderEventsQueue}")
    private String orderEventsQueue;

    private final JmsTemplate jmsTemplate;

    public OrderEventsPublisher(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    public void publish(String body) {
        jmsTemplate.convertAndSend(orderEventsQueue, body);
    }
}
