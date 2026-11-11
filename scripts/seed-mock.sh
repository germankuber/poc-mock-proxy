#!/usr/bin/env bash
set -euo pipefail
docker exec -i "${MOCK_SERVER_MONGO_CONTAINER:-mock-server-mongo-1}" mongosh --quiet "${MOCK_SERVER_MONGO_DB:-mocks}" <<'JS'
db["mocks"].deleteMany({name: "poc-bank-fake"});
db["mocks"].insertOne({
  name: "poc-bank-fake",
  middleware: {name: "bank-fake", partnerKeyName: "poc", baseUrl: "https://bank-fake:8443", deletedAt: null},
  endpoints: [{
    method: "GET",
    url: "/v1/accounts/:id",
    deletedAt: null,
    responses: [{
      label: "ok", description: "poc mock response", statusCode: 200,
      body: {origin: "mock"}, headers: {}, delay: 0, default: true,
      rules: [], rulesOperator: "AND", overrides: [], deletedAt: null
    }]
  }],
  deletedAt: null,
  createdAt: new Date(),
  updatedAt: new Date()
});
JS
