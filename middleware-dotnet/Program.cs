using System.Net;
using System.Net.Http.Json;
using System.Net.Security;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using System.Text.Json.Nodes;

const string certsDir = "/certs";
var bankBaseUrl = Environment.GetEnvironmentVariable("BANK_BASE_URL")
    ?? throw new InvalidOperationException("missing env BANK_BASE_URL");
var caBundle = EnvOr("CA_BUNDLE", $"{certsDir}/bundle-with-dev-ca.crt");
var proxyEnv = EnvOr("HTTPS_PROXY", Environment.GetEnvironmentVariable("https_proxy") ?? "");

string EnvOr(string name, string fallback)
{
    var value = Environment.GetEnvironmentVariable(name);
    return string.IsNullOrEmpty(value) ? fallback : value;
}

var trustedRoots = new X509Certificate2Collection();
trustedRoots.ImportFromPemFile(caBundle);

var clientCertificate = X509Certificate2.CreateFromPemFile(
    $"{certsDir}/middleware-client.crt", $"{certsDir}/middleware-client.key");
clientCertificate = new X509Certificate2(clientCertificate.Export(X509ContentType.Pfx));

bool IsTrusted(X509Certificate? presented, SslPolicyErrors errors)
{
    if (presented is null) return false;
    using var certificate = new X509Certificate2(presented);
    if ((errors & SslPolicyErrors.RemoteCertificateNameMismatch) != 0) return false;
    using var chain = new X509Chain();
    chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
    chain.ChainPolicy.CustomTrustStore.AddRange(trustedRoots);
    chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
    return chain.Build(certificate);
}

var handler = new SocketsHttpHandler
{
    PooledConnectionLifetime = TimeSpan.Zero,
    PooledConnectionIdleTimeout = TimeSpan.Zero,
    UseProxy = proxyEnv != "",
    Proxy = proxyEnv != "" ? new WebProxy(proxyEnv) : null,
    SslOptions = new SslClientAuthenticationOptions
    {
        ClientCertificates = new X509CertificateCollection { clientCertificate },
        RemoteCertificateValidationCallback = (_, certificate, _, errors) => IsTrusted(certificate, errors),
    },
};
var client = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(15) };

JsonNode? ProxyNode() => proxyEnv == "" ? null : JsonValue.Create(proxyEnv);

string DescribeChain(Exception error)
{
    var parts = new List<string>();
    for (var current = error; current is not null; current = current.InnerException!)
    {
        parts.Add($"{current.GetType().Name}: {current.Message}");
        if (current.InnerException is null) break;
    }
    return string.Join(" <- ", parts);
}

IResult Failure(string message) => Results.Json(
    new JsonObject { ["error"] = message, ["proxy_env"] = ProxyNode() },
    statusCode: StatusCodes.Status502BadGateway);

var app = WebApplication.CreateBuilder(args).Build();
app.Urls.Add("http://0.0.0.0:9000");

app.MapGet("/health", () => Results.Json(new JsonObject { ["status"] = "ok" }));

app.MapGet("/accounts/{id}", async (string id) =>
{
    try
    {
        using var response = await client.GetAsync($"{bankBaseUrl}/v1/accounts/{id}");
        var status = (int)response.StatusCode;
        if (status >= 400) return Failure($"upstream {status}");
        var upstream = await response.Content.ReadFromJsonAsync<JsonNode>();
        return Results.Json(new JsonObject
        {
            ["upstream_status"] = status,
            ["upstream"] = upstream,
            ["proxy_env"] = ProxyNode(),
        });
    }
    catch (Exception error)
    {
        return Failure(DescribeChain(error));
    }
});

app.Run();
