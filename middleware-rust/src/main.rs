use std::{env, error::Error, fs, sync::Arc, time::Duration};

use axum::{
    extract::{Path, State},
    http::StatusCode,
    routing::get,
    Json, Router,
};
use reqwest::{Certificate, Client, Identity};
use serde_json::{json, Value};

const CERTS: &str = "/certs";

struct App {
    client: Client,
    bank_base_url: String,
    proxy_env: Value,
}

type Reply = (StatusCode, Json<Value>);

fn env_or(name: &str, fallback: &str) -> String {
    env::var(name)
        .ok()
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| fallback.to_string())
}

fn proxy_in_use() -> Value {
    ["HTTPS_PROXY", "https_proxy"]
        .iter()
        .filter_map(|name| env::var(name).ok())
        .find(|value| !value.is_empty())
        .map_or(Value::Null, Value::String)
}

fn split_pem_certificates(pem: &str) -> Vec<String> {
    const END: &str = "-----END CERTIFICATE-----";
    pem.split(END)
        .filter(|chunk| chunk.contains("-----BEGIN CERTIFICATE-----"))
        .map(|chunk| format!("{}{}\n", chunk.trim_start(), END))
        .collect()
}

fn build_client() -> Result<Client, Box<dyn Error>> {
    let bundle = fs::read_to_string(env_or(
        "CA_BUNDLE",
        &format!("{CERTS}/bundle-with-dev-ca.crt"),
    ))?;
    let mut builder = Client::builder()
        .use_rustls_tls()
        .tls_built_in_root_certs(false)
        .pool_max_idle_per_host(0)
        .timeout(Duration::from_secs(15));
    for pem in split_pem_certificates(&bundle) {
        builder = builder.add_root_certificate(Certificate::from_pem(pem.as_bytes())?);
    }
    let mut identity_pem = fs::read(format!("{CERTS}/middleware-client.crt"))?;
    identity_pem.extend(fs::read(format!("{CERTS}/middleware-client.key"))?);
    Ok(builder.identity(Identity::from_pem(&identity_pem)?).build()?)
}

fn error_chain(error: &dyn Error) -> String {
    let mut message = error.to_string();
    let mut source = error.source();
    while let Some(cause) = source {
        message.push_str(&format!(" <- {cause}"));
        source = cause.source();
    }
    message
}

fn failure(app: &App, message: String) -> Reply {
    (
        StatusCode::BAD_GATEWAY,
        Json(json!({"error": message, "proxy_env": app.proxy_env})),
    )
}

async fn fetch_account(app: &App, id: &str) -> Result<Reply, reqwest::Error> {
    let response = app
        .client
        .get(format!("{}/v1/accounts/{id}", app.bank_base_url))
        .send()
        .await?;
    let status = response.status();
    if status.as_u16() >= 400 {
        return Ok(failure(app, format!("upstream {}", status.as_u16())));
    }
    let upstream: Value = response.json().await?;
    Ok((
        StatusCode::OK,
        Json(json!({
            "upstream_status": status.as_u16(),
            "upstream": upstream,
            "proxy_env": app.proxy_env,
        })),
    ))
}

async fn account(State(app): State<Arc<App>>, Path(id): Path<String>) -> Reply {
    match fetch_account(&app, &id).await {
        Ok(reply) => reply,
        Err(error) => failure(&app, format!("reqwest::Error: {}", error_chain(&error))),
    }
}

async fn health() -> Reply {
    (StatusCode::OK, Json(json!({"status": "ok"})))
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let app = Arc::new(App {
        client: build_client()?,
        bank_base_url: env::var("BANK_BASE_URL")?,
        proxy_env: proxy_in_use(),
    });
    let router = Router::new()
        .route("/health", get(health))
        .route("/accounts/:id", get(account))
        .with_state(app);
    let listener = tokio::net::TcpListener::bind("0.0.0.0:9000").await?;
    axum::serve(listener, router).await?;
    Ok(())
}
