#!/usr/bin/env bash
# Local mirror of .github/workflows/ci-cd.yml - every stage is a gate; any failure stops the delivery.
set -o pipefail
PY=${PY:-python3}
stage() { echo; echo "===== $1 ====="; shift; if "$@"; then echo "----- PASSED -----"; else echo "----- FAILED: pipeline stopped -----"; exit 1; fi; }
stage "Gate 1a: lint (flake8)"            $PY -m flake8 app tests
stage "Gate 1b: unit tests + coverage"    $PY -m pytest -q -p no:cacheprovider tests/test_unit.py --cov=app --cov-fail-under=85
stage "Gate 2a: SAST (bandit)"            $PY -m bandit -q -r app -ll
stage "Gate 2b: dependency CVEs (pip-audit)" $PY -m pip_audit -r requirements.txt --progress-spinner off
stage "Gate 2c: IaC gate - app workloads (checkov)" checkov --quiet --compact -f k8s/base/30-app.yaml -f k8s/base/60-network-policy.yaml --framework kubernetes --config-file .checkov.yaml --skip-check CKV_K8S_35,CKV_K8S_43,CKV_K8S_15 --skip-download
stage "Gate 2d: IaC report - whole platform (checkov, non-blocking)" bash -c "checkov --quiet --compact --skip-download -d k8s --framework kubernetes --config-file .checkov.yaml --soft-fail | grep -E 'Passed checks|Failed checks' || true"
stage "Gate 3: integration tests vs live deployment" env BASE_URL="${BASE_URL:?set BASE_URL}" $PY -m pytest -q -p no:cacheprovider tests/test_integration.py
