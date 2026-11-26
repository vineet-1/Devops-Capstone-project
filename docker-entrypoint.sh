#!/bin/bash
set -euo pipefail
if [ "${1:-postgres}" != "postgres" ]; then exec "$@"; fi
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
USER_NAME=${POSTGRES_USER:-postgres}; DB=${POSTGRES_DB:-$USER_NAME}
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  mkdir -p "$PGDATA" && chmod 700 "$PGDATA"
  PWFILE=$(mktemp); printf '%s' "$POSTGRES_PASSWORD" > "$PWFILE"
  initdb -D "$PGDATA" -U "$USER_NAME" --pwfile="$PWFILE" --auth-host=scram-sha-256 --auth-local=trust >/dev/null
  rm -f "$PWFILE"
  echo "host all all 0.0.0.0/0 scram-sha-256" >> "$PGDATA/pg_hba.conf"
  pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start >/dev/null
  [ "$DB" != "postgres" ] && createdb -U "$USER_NAME" "$DB" || true
  pg_ctl -D "$PGDATA" -m fast -w stop >/dev/null
  echo "database initialised"
fi
exec postgres -D "$PGDATA" -c listen_addresses='*'
