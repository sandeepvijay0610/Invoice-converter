package com.kaavian.invoice_api.config;

import com.kaavian.invoice_api.repository.UserRepository;
import com.kaavian.invoice_api.security.ClerkJwtFilter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

import java.util.List;

@Configuration
public class WebConfig {

    @Value("${cors.allowed-origins:http://localhost:5173}")
    private String allowedOrigins;

    @Value("${clerk.jwks-url}")
    private String jwksUrl;

    @Value("${clerk.issuer}")
    private String clerkIssuer;

    @Bean
    public FilterRegistrationBean<CorsFilter> corsFilter() {
        CorsConfiguration config = new CorsConfiguration();
        config.setAllowedOrigins(List.of(allowedOrigins.split(",")));
        config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
        config.setAllowedHeaders(List.of("*"));
        config.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", config);
        // ADDED THIS LINE: Tell CORS to allow SAP to read the OData feed
        source.registerCorsConfiguration("/odata/**", config); 

        FilterRegistrationBean<CorsFilter> bean = new FilterRegistrationBean<>(new CorsFilter(source));
        bean.setOrder(0);
        return bean;
    }

    @Bean
    public FilterRegistrationBean<ClerkJwtFilter> clerkJwtFilter(UserRepository userRepository) throws Exception {
        ClerkJwtFilter filter = new ClerkJwtFilter(userRepository, jwksUrl, clerkIssuer);

        FilterRegistrationBean<ClerkJwtFilter> bean = new FilterRegistrationBean<>(filter);
        bean.addUrlPatterns("/api/*");
        bean.setOrder(1);
        return bean;
    }
}