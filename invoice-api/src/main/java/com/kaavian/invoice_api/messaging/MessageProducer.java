package com.kaavian.invoice_api.messaging;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class MessageProducer {

    private final RabbitTemplate rabbitTemplate;

    // Must match the queue name declared in RabbitMQConfig and consumed by the Python worker.
    private static final String QUEUE_NAME = "invoice_requests";

    public MessageProducer(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendExtractionRequest(String docId, String filePath) {
        // Build the JSON payload the Python worker expects.
        String jsonPayload = String.format("{\"doc_id\": \"%s\", \"file_path\": \"%s\"}", docId, filePath);

        // FIX #4: Set content-type header AND actually send the Message object.
        // Previously a Message was constructed with the JSON content-type header,
        // but then discarded — convertAndSend() was called with the raw String
        // instead, so the header was silently lost.
        MessageProperties properties = new MessageProperties();
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        Message message = new Message(jsonPayload.getBytes(), properties);

        rabbitTemplate.send(QUEUE_NAME, message);

        System.out.println("Fired extraction request to RabbitMQ: " + jsonPayload);
    }
}