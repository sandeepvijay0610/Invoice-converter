package com.kaavian.invoice_api.messaging;

import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Service;

@Service
public class MessageProducer {

    private final RabbitTemplate rabbitTemplate;
    
    // This must match the queue name in your Python worker exactly
    private static final String QUEUE_NAME = "invoice_requests";

    public MessageProducer(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void sendExtractionRequest(String docId, String filePath) {
        // 1. Build the exact JSON string your Python worker expects
        String jsonPayload = String.format("{\"doc_id\": \"%s\", \"file_path\": \"%s\"}", docId, filePath);

        // 2. Force the content type to JSON so Python parses it cleanly
        MessageProperties properties = new MessageProperties();
        properties.setContentType(MessageProperties.CONTENT_TYPE_JSON);
        Message message = new Message(jsonPayload.getBytes(), properties);

        // 3. Fire and forget! Drop it into the RabbitMQ queue
        rabbitTemplate.convertAndSend("", QUEUE_NAME, jsonPayload);
        
        System.out.println("🚀 Fired extraction request to RabbitMQ: " + jsonPayload);
    }
}