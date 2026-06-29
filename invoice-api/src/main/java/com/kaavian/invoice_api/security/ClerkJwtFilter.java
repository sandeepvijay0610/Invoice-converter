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
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.net.URL;
import java.security.interfaces.RSAPublicKey;
import java.util.concurrent.TimeUnit;

// Not a @Component — instantiated manually in WebConfig to prevent
// Spring registering it twice (once via scan, once via @Bean).
public class ClerkJwtFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(ClerkJwtFilter.class);

    private final JwkProvider jwkProvider;
    private final UserRepository userRepository;
    private final String clerkIssuer;

    public ClerkJwtFilter(UserRepository userRepository,
                          String jwksUrl,
                          String clerkIssuer) throws Exception {
        this.userRepository = userRepository;
        this.clerkIssuer = clerkIssuer;
        // Cache up to 5 public keys for 10 minutes — avoids a JWKS network
        // call on every request while still picking up Clerk key rotations
        this.jwkProvider = new JwkProviderBuilder(new URL(jwksUrl))
                .cached(5, 10, TimeUnit.MINUTES)
                .build();
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        // Skip CORS preflight AND skip the new SAP OData endpoint
        String path = request.getServletPath();
        return "OPTIONS".equalsIgnoreCase(request.getMethod()) || path.startsWith("/odata/");
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {

        String authHeader = request.getHeader("Authorization");

        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            log.warn("JWT rejected — missing or malformed Authorization header on {} {}",
                    request.getMethod(), request.getServletPath());
            sendError(response, HttpServletResponse.SC_UNAUTHORIZED,
                    "Missing or invalid Authorization header");
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
                    // TODO: Reduce to 60L before production deployment.
                    // 864000L (10 days) is only here to handle WSL2/Docker clock drift in local dev.
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
            log.warn("JWT verification failed: {}", e.getMessage());
            sendError(response, HttpServletResponse.SC_UNAUTHORIZED, "Invalid or expired token");
            return;
        } catch (Exception e) {
            log.error("Unexpected auth error: {}", e.getMessage(), e);
            sendError(response, HttpServletResponse.SC_INTERNAL_SERVER_ERROR,
                    "Authentication error: " + e.getMessage());
            return;
        }

        filterChain.doFilter(request, response);
    }

    private void sendError(HttpServletResponse response, int status, String message)
            throws IOException {
        response.setStatus(status);
        response.setContentType("application/json");
        response.getWriter().write("{\"error\":\"" + message + "\"}");
    }
}