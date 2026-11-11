#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../certs"
/bin/rm -rf ./*
openssl req -x509 -newkey rsa:2048 -nodes -keyout bank-ca.key -out bank-ca.crt -days 30 -subj "/CN=poc-bank-ca" 2>/dev/null
openssl req -x509 -newkey rsa:2048 -nodes -keyout dev-ca.key -out dev-ca.crt -days 30 -subj "/CN=poc-dev-ca" \
  -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -keyout bank-fake.key -out bank-fake.csr -subj "/CN=bank-fake" 2>/dev/null
printf "subjectAltName=DNS:bank-fake\nextendedKeyUsage=serverAuth\n" > bank-fake.ext
openssl x509 -req -in bank-fake.csr -CA bank-ca.crt -CAkey bank-ca.key -CAcreateserial -out bank-fake.crt -days 30 -extfile bank-fake.ext 2>/dev/null
openssl req -newkey rsa:2048 -nodes -keyout middleware-client.key -out middleware-client.csr -subj "/CN=middleware-client" 2>/dev/null
printf "extendedKeyUsage=clientAuth\n" > client.ext
openssl x509 -req -in middleware-client.csr -CA bank-ca.crt -CAkey bank-ca.key -CAcreateserial -out middleware-client.crt -days 30 -extfile client.ext 2>/dev/null
cat bank-ca.crt dev-ca.crt > bundle-with-dev-ca.crt
cp bank-ca.crt bundle-bank-only.crt
mkdir -p mitm-confdir
cat dev-ca.key dev-ca.crt > mitm-confdir/mitmproxy-ca.pem
cp dev-ca.crt mitm-confdir/mitmproxy-ca-cert.pem
/bin/rm -f ./*.csr ./*.ext ./*.srl
chmod -R a+rX .
chmod a+rw mitm-confdir
chmod a+r ./*.key mitm-confdir/*
echo "certs generated"
