#!/usr/bin/env bash
# Restore PostgreSQL from the latest (or given) backup on the db-backups volume.
# Usage: scripts/restore_db.sh [backup-file-name]
set -euo pipefail
FILE=${1:-latest}
kubectl -n taskapi delete job db-restore --ignore-not-found
cat <<YAML | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata: { name: db-restore, namespace: taskapi }
spec:
  backoffLimit: 0
  template:
    metadata: { labels: { app: db-backup } }
    spec:
      restartPolicy: Never
      automountServiceAccountToken: false
      containers:
        - name: restore
          image: ${PG_IMAGE:-postgres:16-alpine}
          command: ["sh", "-c"]
          args:
            - |
              set -e
              for i in \$(seq 1 30); do pg_isready -q -h postgres && break; sleep 2; done
              F=\$( [ "$FILE" = latest ] && ls -1t /backups/*.sql.gz | head -1 || echo /backups/$FILE )
              cd /backups && sha256sum -c "\$(basename \$F).sha256"
              psql -h postgres -U "\$PGUSER" -d tasks -v ON_ERROR_STOP=1 -c 'DROP TABLE IF EXISTS tasks'
              gunzip -c "\$F" > /tmp/restore.sql
              psql -h postgres -U "\$PGUSER" -d tasks -v ON_ERROR_STOP=1 -q -f /tmp/restore.sql
              echo "restored \$F: \$(psql -h postgres -U \$PGUSER -d tasks -tAc 'SELECT count(*) FROM tasks') tasks"
          env:
            - { name: PGUSER, valueFrom: { secretKeyRef: { name: taskapi-db, key: username } } }
            - { name: PGPASSWORD, valueFrom: { secretKeyRef: { name: taskapi-db, key: password } } }
          volumeMounts: [{ name: backups, mountPath: /backups }]
      volumes: [{ name: backups, persistentVolumeClaim: { claimName: db-backups } }]
YAML
kubectl -n taskapi wait --for=condition=complete job/db-restore --timeout=120s
