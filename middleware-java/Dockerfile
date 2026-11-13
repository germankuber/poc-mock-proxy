FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY Middleware.java ./
RUN javac -d /out Middleware.java

FROM eclipse-temurin:21-jre
COPY --from=build /out /app
ENTRYPOINT ["java", "-cp", "/app", "Middleware"]
