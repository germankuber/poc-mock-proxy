package main

import (
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

const certsDir = "/certs"

var (
	bankBaseURL = mustEnv("BANK_BASE_URL")
	caBundle    = envOr("CA_BUNDLE", certsDir+"/bundle-with-dev-ca.crt")
)

func mustEnv(name string) string {
	value := os.Getenv(name)
	if value == "" {
		log.Fatalf("missing env %s", name)
	}
	return value
}

func envOr(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}

func proxyInUse() any {
	if value := envOr("HTTPS_PROXY", os.Getenv("https_proxy")); value != "" {
		return value
	}
	return nil
}

func buildClient() (*http.Client, error) {
	pem, err := os.ReadFile(caBundle)
	if err != nil {
		return nil, err
	}
	roots := x509.NewCertPool()
	if !roots.AppendCertsFromPEM(pem) {
		return nil, fmt.Errorf("no certificates found in %s", caBundle)
	}
	pair, err := tls.LoadX509KeyPair(certsDir+"/middleware-client.crt", certsDir+"/middleware-client.key")
	if err != nil {
		return nil, err
	}
	transport := &http.Transport{
		Proxy:             http.ProxyFromEnvironment,
		DisableKeepAlives: true,
		TLSClientConfig:   &tls.Config{RootCAs: roots, Certificates: []tls.Certificate{pair}},
	}
	return &http.Client{Transport: transport, Timeout: 15 * time.Second}, nil
}

func reply(w http.ResponseWriter, status int, payload any) {
	body, _ := json.Marshal(payload)
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	w.Write(body)
}

func fail(w http.ResponseWriter, message string) {
	reply(w, http.StatusBadGateway, map[string]any{"error": message, "proxy_env": proxyInUse()})
}

func accounts(client *http.Client) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		id := strings.TrimPrefix(r.URL.Path, "/accounts/")
		if id == "" || strings.Contains(id, "/") {
			reply(w, http.StatusNotFound, map[string]any{"error": "not found"})
			return
		}
		response, err := client.Get(bankBaseURL + "/v1/accounts/" + id)
		if err != nil {
			fail(w, fmt.Sprintf("%T: %v", err, err))
			return
		}
		defer response.Body.Close()
		if response.StatusCode >= 400 {
			fail(w, fmt.Sprintf("upstream %d", response.StatusCode))
			return
		}
		raw, err := io.ReadAll(response.Body)
		if err != nil {
			fail(w, fmt.Sprintf("%T: %v", err, err))
			return
		}
		var upstream any
		if err := json.Unmarshal(raw, &upstream); err != nil {
			fail(w, fmt.Sprintf("%T: %v", err, err))
			return
		}
		reply(w, http.StatusOK, map[string]any{
			"upstream_status": response.StatusCode,
			"upstream":        upstream,
			"proxy_env":       proxyInUse(),
		})
	}
}

func main() {
	client, err := buildClient()
	if err != nil {
		log.Fatal(err)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		reply(w, http.StatusOK, map[string]any{"status": "ok"})
	})
	mux.HandleFunc("/accounts/", accounts(client))
	log.Fatal(http.ListenAndServe("0.0.0.0:9000", mux))
}
