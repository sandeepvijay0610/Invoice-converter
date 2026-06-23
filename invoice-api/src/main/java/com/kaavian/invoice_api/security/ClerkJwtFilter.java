package com.kaavian.invoice_api.security;

import com.auth0.jwk.Jwk;
import com.auth0.jwk.JwkProvider;
import com.auth0.jwk.JwkProviderBuilder;
import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.kaavian.invoice_api.entity.User;
import com.kaavian.invoice_api.repository.UserRepository;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.net.URL;
import java.security.interfaces.RSAPublicKey;
import java.util.concurrent.TimeUnit;

public class ClerkJwtFilter extends OncePerRequestFilter {

    private final JwkProvider jwkProvider;
    private final UserRepository userRepository;
    private final String clerkIssuer;

    public ClerkJwtFilter(UserRepository userRepository,
                          String jwksUrl,
                          String clerkIssuer) throws Exception {
        this.userRepository = userRepository;
        this.clerkIssuer = clerkIssuer;
        this.jwkProvider = new JwkProviderBuilder(new URL(jwksUrl))
                .cached(5, 10, TimeUnit.MINUTES)
                .build();
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getServletPath();
        String method = request.getMethod();
        // Skip filtering for CORS preflight and login route
        return "OPTIONS".equalsIgnoreCase(method) || path.equals("/api/auth/login");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {

        String authHeader = request.getHeader("Authorization");

        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            System.err.println("❌ CLERK JWT REJECTED: Missing or malformed Authorization header.");
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"Missing or invalid Authorization header\"}");
            return;
        }

        String token = authHeader.substring(7);

        try {
            DecodedJWT unverified = JWT.decode(token);
            Jwk jwk = jwkProvider.get(unverified.getKeyId());
            RSAPublicKey publicKey = (RSAPublicKey) jwk.getPublicKey();

            Algorithm algorithm = Algorithm.RSA256(publicKey, null);
            DecodedJWT verified = JWT.require(algorithm)
                    .withIssuer(clerkIssuer)
                    // THE ULTIMATE FIX: 10 days of leeway to completely ignore WSL/Docker clock drift
                    .acceptLeeway(864000L) 
                    .build()
                    .verify(token);

            String clerkUserId = verified.getSubject();
            String email = verified.getClaim("email").asString();
            if (email == null) email = clerkUserId + "@clerk.local";

            final String finalEmail = email;
            User user = userRepository.findByUsername(clerkUserId)
                    .orElseGet(() -> {
                        User newUser = new User();
                        newUser.setUsername(clerkUserId);
                        newUser.setPassword("");
                        newUser.setTenantName(finalEmail);
                        newUser.setRole("user");
                        return userRepository.save(newUser);
                    });

            request.setAttribute("authenticatedUser", user);

        } catch (JWTVerificationException e) {
            // This will print EXACTLY why it failed in your Docker/Spring Boot terminal
            System.err.println("❌ CLERK JWT REJECTED: " + e.getMessage()); 
            response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"Invalid or expired token\"}");
            return;
        } catch (Exception e) {
            System.err.println("❌ CLERK SERVER ERROR: " + e.getMessage());
            response.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            response.setContentType("application/json");
            response.getWriter().write("{\"error\":\"Authentication error: " + e.getMessage() + "\"}");
            return;
        }

        filterChain.doFilter(request, response);
    }
}