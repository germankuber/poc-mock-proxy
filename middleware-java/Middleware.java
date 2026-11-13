import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyFactory;
import java.security.KeyStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.spec.PKCS8EncodedKeySpec;
import java.time.Duration;
import java.util.Base64;
import java.util.Collection;
import java.util.concurrent.Executors;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class Middleware {
    static final String CERTS = "/certs";
    static final String BANK_BASE_URL = System.getenv("BANK_BASE_URL");
    static final String CA_BUNDLE = envOr("CA_BUNDLE", CERTS + "/bundle-with-dev-ca.crt");
    static final String PROXY = envOr("HTTPS_PROXY", System.getenv("https_proxy"));

    static String envOr(String name, String fallback) {
        String value = System.getenv(name);
        return value == null || value.isEmpty() ? fallback : value;
    }

    static Collection<? extends Certificate> readCertificates(Path path) throws Exception {
        return CertificateFactory.getInstance("X.509").generateCertificates(Files.newInputStream(path));
    }

    static byte[] readPem(Path path) throws Exception {
        String pem = Files.readString(path)
                .replaceAll("-----(BEGIN|END) [A-Z ]+-----", "")
                .replaceAll("\\s", "");
        return Base64.getDecoder().decode(pem);
    }

    static SSLContext buildSslContext() throws Exception {
        KeyStore trust = KeyStore.getInstance(KeyStore.getDefaultType());
        trust.load(null, null);
        int index = 0;
        for (Certificate certificate : readCertificates(Path.of(CA_BUNDLE))) {
            trust.setCertificateEntry("ca-" + index++, certificate);
        }
        TrustManagerFactory trustFactory = TrustManagerFactory.getInstance(TrustManagerFactory.getDefaultAlgorithm());
        trustFactory.init(trust);

        Certificate[] chain = readCertificates(Path.of(CERTS + "/middleware-client.crt")).toArray(new Certificate[0]);
        var privateKey = KeyFactory.getInstance("RSA")
                .generatePrivate(new PKCS8EncodedKeySpec(readPem(Path.of(CERTS + "/middleware-client.key"))));
        char[] password = new char[0];
        KeyStore identity = KeyStore.getInstance(KeyStore.getDefaultType());
        identity.load(null, null);
        identity.setKeyEntry("client", privateKey, password, chain);
        KeyManagerFactory keyFactory = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm());
        keyFactory.init(identity, password);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keyFactory.getKeyManagers(), trustFactory.getTrustManagers(), null);
        return context;
    }

    static HttpClient buildClient(SSLContext sslContext) {
        HttpClient.Builder builder = HttpClient.newBuilder()
                .sslContext(sslContext)
                .connectTimeout(Duration.ofSeconds(15));
        if (PROXY != null) {
            URI proxy = URI.create(PROXY);
            builder.proxy(ProxySelector.of(new InetSocketAddress(proxy.getHost(), proxy.getPort())));
        }
        return builder.build();
    }

    static String quote(String value) {
        StringBuilder out = new StringBuilder("\"");
        for (char c : value.toCharArray()) {
            switch (c) {
                case '"' -> out.append("\\\"");
                case '\\' -> out.append("\\\\");
                case '\n' -> out.append("\\n");
                case '\r' -> out.append("\\r");
                case '\t' -> out.append("\\t");
                default -> {
                    if (c < 0x20) out.append(String.format("\\u%04x", (int) c));
                    else out.append(c);
                }
            }
        }
        return out.append('"').toString();
    }

    static String proxyJson() {
        return PROXY == null ? "null" : quote(PROXY);
    }

    static String describe(Throwable error) {
        StringBuilder message = new StringBuilder();
        for (Throwable current = error; current != null; current = current.getCause()) {
            if (message.length() > 0) message.append(" <- ");
            message.append(current.getClass().getSimpleName()).append(": ").append(current.getMessage());
            if (current.getCause() == current) break;
        }
        return message.toString();
    }

    static void reply(HttpExchange exchange, int status, String json) throws IOException {
        byte[] body = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json");
        exchange.sendResponseHeaders(status, body.length);
        exchange.getResponseBody().write(body);
        exchange.close();
    }

    static void fail(HttpExchange exchange, String message) throws IOException {
        reply(exchange, 502, "{\"error\":" + quote(message) + ",\"proxy_env\":" + proxyJson() + "}");
    }

    static void accounts(HttpExchange exchange, SSLContext sslContext) throws IOException {
        String id = exchange.getRequestURI().getPath().substring("/accounts/".length());
        if (id.isEmpty() || id.contains("/")) {
            reply(exchange, 404, "{\"error\":\"not found\"}");
            return;
        }
        try {
            HttpRequest request = HttpRequest.newBuilder(URI.create(BANK_BASE_URL + "/v1/accounts/" + id))
                    .timeout(Duration.ofSeconds(15))
                    .GET()
                    .build();
            HttpResponse<String> response = buildClient(sslContext).send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 400) {
                fail(exchange, "upstream " + response.statusCode());
                return;
            }
            reply(exchange, 200, "{\"upstream_status\":" + response.statusCode()
                    + ",\"upstream\":" + response.body().strip()
                    + ",\"proxy_env\":" + proxyJson() + "}");
        } catch (Exception error) {
            fail(exchange, describe(error));
        }
    }

    public static void main(String[] args) throws Exception {
        SSLContext sslContext = buildSslContext();
        HttpServer server = HttpServer.create(new InetSocketAddress("0.0.0.0", 9000), 0);
        server.createContext("/health", exchange -> reply(exchange, 200, "{\"status\":\"ok\"}"));
        server.createContext("/accounts/", exchange -> accounts(exchange, sslContext));
        server.setExecutor(Executors.newCachedThreadPool());
        server.start();
    }
}
