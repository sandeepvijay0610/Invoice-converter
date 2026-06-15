package com.kaavian.invoice_api.config;

import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMQConfig {

    @Bean
    public Queue invoiceRequestsQueue() {
        return new Queue("invoice_requests", true); // true = durable
    }
}