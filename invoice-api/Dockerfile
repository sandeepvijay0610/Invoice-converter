# ---- Stage 1: build the Spring Boot jar ----
FROM maven:3.9-eclipse-temurin-17 AS builder

WORKDIR /build

COPY pom.xml .
RUN mvn dependency:go-offline -q

COPY src ./src
RUN mvn package -DskipTests -q


# ---- Stage 2: minimal runtime image --------
FROM eclipse-temurin:17-jre-jammy AS runtime

RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /app

COPY --from=builder /build/target/*.jar app.jar
RUN chown appuser:appuser app.jar
USER appuser

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "app.jar"]