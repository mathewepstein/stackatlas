package com.acme.orders;

import org.springframework.jms.annotation.JmsListener;

public class OrderEventsListener {
    @JmsListener(destination = "${aws.sqs.orderEventsQueue}", containerFactory = "jmsListenerContainerFactory")
    public void onEvent(String body) {
    }
}
