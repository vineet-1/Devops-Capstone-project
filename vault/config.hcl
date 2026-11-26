storage "file" { path = "vault/.data" }
listener "tcp" {
  address     = "127.0.0.1:8200"
  tls_disable = true   # lab only; production: TLS certs + KMS auto-unseal
}
api_addr      = "http://127.0.0.1:8200"
disable_mlock = true
