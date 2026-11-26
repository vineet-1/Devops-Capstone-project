#!/usr/bin/env bash
# Idempotent vault bootstrap: start, init (Shamir 5/3), unseal, enable engines, seed DB secret, create AppRole.
set -euo pipefail
cd "$(dirname "$0")/.."
export BAO_ADDR=http://127.0.0.1:8200
if ! curl -s $BAO_ADDR/v1/sys/health >/dev/null; then
  mkdir -p vault/.data && nohup bao server -config=vault/config.hcl > vault/.data/server.log 2>&1 &
  for i in $(seq 1 20); do curl -s $BAO_ADDR/v1/sys/health >/dev/null && break; sleep 1; done
fi
if [ "$(bao status -format=json | python3 -c 'import sys,json;print(json.load(sys.stdin)["initialized"])')" = "False" ]; then
  bao operator init -key-shares=5 -key-threshold=3 -format=json > vault/init.json
  chmod 600 vault/init.json
  echo "vault initialised (5 key shares, threshold 3)"
fi
for i in 0 1 2; do
  bao status >/dev/null 2>&1 && break
  bao operator unseal "$(python3 -c "import json;print(json.load(open('vault/init.json'))['unseal_keys_b64'][$i])")" >/dev/null
done
export BAO_TOKEN=$(python3 -c "import json;print(json.load(open('vault/init.json'))['root_token'])")
grep -q '^secret/' <<<"$(bao secrets list)" || bao secrets enable -path=secret kv-v2 >/dev/null
grep -q '^approle/' <<<"$(bao auth list)" || bao auth enable approle >/dev/null
grep -q '^file/' <<<"$(bao audit list 2>/dev/null)" || bao audit enable file file_path="$PWD/vault/.data/audit.log" >/dev/null
if ! bao kv get secret/taskapi/db >/dev/null 2>&1; then
  PW=$(python3 -c "import secrets,string;print(''.join(secrets.choice(string.ascii_letters+string.digits) for _ in range(32)))")
  bao kv put secret/taskapi/db username=taskapi password="$PW" >/dev/null && echo "generated and stored random 32-char DB password"
fi
bao policy write deployer vault/policies/deployer.hcl >/dev/null
bao write auth/approle/role/deployer token_policies=deployer token_ttl=10m secret_id_ttl=15m secret_id_num_uses=1 >/dev/null
echo "vault ready: sealed=$(bao status -format=json | python3 -c 'import sys,json;print(json.load(sys.stdin)["sealed"])')"
