# DevOps Capstone - Task Manager API platform

**Sahil Chaudhary · Roll No. 2301730193 · DevOps and Automation Lab · K.R. Mangalam University**

An end-to-end DevOps automation platform that takes a Flask + PostgreSQL REST API from **code commit to production on Kubernetes**, with observability, security and recoverability built in.

| Area | Implementation |
|---|---|
| Version control | Git, trunk-based (`main`), conventional commits, PR-gated pipeline |
| CI/CD | GitHub Actions (`.github/workflows/ci-cd.yml`) + identical local runner (`scripts/run_pipeline.sh`) |
| Quality gates | flake8, pytest unit tests (coverage ≥ 85 %), integration tests against PostgreSQL |
| Security | Bandit (SAST), pip-audit (CVEs), Checkov (IaC), OpenBao/Vault secrets, NetworkPolicies, non-root read-only containers, RBAC |
| Containerization | Multi-stage, non-root Dockerfile with healthcheck |
| Orchestration | Kubernetes (k3s): Deployments, StatefulSet, HPA, PDB, probes, Traefik ingress |
| Infrastructure automation | Ansible (`ansible/site.yml`) - k3s, images, secrets, deploy, verify; kustomize overlays |
| Monitoring | Prometheus (SLO recording rules + alerts) → Alertmanager |
| Logging | Structured JSON logs → Promtail → Loki (LogQL) |
| Deployment strategy | Progressive canary with automated Prometheus analysis + auto-rollback (`scripts/canary_rollout.py`) |
| Recoverability | Scheduled verified `pg_dump` backups (CronJob), `scripts/restore_db.sh`, self-healing, PDB |

## Quick start
```bash
cd ansible && ansible-playbook site.yml                 # provision everything (idempotent)
BASE_URL=http://<ingress> ./scripts/run_pipeline.sh     # all pipeline gates locally
python3 scripts/canary_rollout.py --image taskapi:1.1.0 --version 1.1.0 --generate-load
./scripts/restore_db.sh                                 # restore latest verified backup
```

## Layout
```
app/                Flask API (health/readiness probes, /metrics, JSON logs)
tests/              unit + integration tests
Dockerfile          production image; docker/ = offline-lab images (postgres, monitoring)
k8s/base            app, database, traffic split, HPA/PDB, NetworkPolicies, backups
k8s/monitoring      Prometheus, Alertmanager, Loki, Promtail
k8s/overlays/local  image mapping for the offline lab cluster
ansible/            infrastructure automation (roles: preflight, k3s, images, secrets, deploy, verify)
vault/              OpenBao/Vault bootstrap + least-privilege policy
scripts/            pipeline runner, canary controller, restore, probes
```
The full report with evidence is in the submitted PDF.
