#!/usr/bin/env python3
"""Progressive canary rollout with automated Prometheus analysis.

Steps: deploy new version as 'canary' -> shift traffic 10% -> 30% -> 60% -> analyse each step
against SLOs and against the stable version -> promote (stable := new) or roll back (canary -> 0%).
Usage: canary_rollout.py --image taskapi:1.1.0 --version 1.1.0 [--generate-load] [--fault-rate 0.15]
"""
import argparse
import json
import random
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

NS = "taskapi"
STEPS = [10, 30, 60]
MAX_ERROR_RATIO = 0.02          # rollback if canary 5xx ratio > 2 %
MAX_ERROR_DELTA = 0.01          # ... or > 1 percentage point worse than stable
MAX_P95_SECONDS = 0.25          # rollback if canary p95 > 250 ms
MAX_P95_RATIO = 2.0             # ... or > 2x the stable p95
MIN_REQUESTS = 50


def sh(cmd):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True).stdout.strip()


def log(msg):
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def prom(query):
    url = f"{PROM}/api/v1/query?" + urllib.parse.urlencode({"query": query})
    data = json.loads(urllib.request.urlopen(url, timeout=10).read())["data"]["result"]
    return {r["metric"].get("track", "all"): float(r["value"][1]) for r in data}


def set_weights(canary):
    patch = {"spec": {"weighted": {"services": [
        {"name": "taskapi-stable", "port": 80, "weight": 100 - canary},
        {"name": "taskapi-canary", "port": 80, "weight": canary}]}}}
    sh(f"kubectl -n {NS} patch traefikservices.traefik.io taskapi-split --type merge -p '{json.dumps(patch)}'")


def load(stop):
    def worker():
        while not stop.is_set():
            path = random.choice(["/api/tasks", "/api/tasks", "/api/tasks?priority=high", "/version"])
            req = urllib.request.Request(INGRESS + path, headers={"X-User-Id": f"user-{random.randint(1, 300)}"})
            try:
                urllib.request.urlopen(req, timeout=3).read()
            except Exception:
                pass
    for _ in range(6):
        threading.Thread(target=worker, daemon=True).start()


def analyse(window):
    reqs = prom(f'sum by (track) (increase(http_requests_total[{window}]))')
    errs = prom(f'sum by (track) (increase(http_requests_total{{status=~"5.."}}[{window}]))')
    p95 = prom(f'histogram_quantile(0.95, sum by (track, le) (rate(http_request_duration_seconds_bucket[{window}])))')
    m = {t: {"req": reqs.get(t, 0), "err": errs.get(t, 0) / reqs[t] if reqs.get(t) else 0, "p95": p95.get(t, 0)}
         for t in ("stable", "canary")}
    c, s = m["canary"], m["stable"]
    fails = []
    if c["req"] < MIN_REQUESTS:
        fails.append(f"insufficient canary traffic ({c['req']:.0f} req)")
    if c["err"] > MAX_ERROR_RATIO:
        fails.append(f"canary error ratio {c['err']:.1%} > {MAX_ERROR_RATIO:.0%}")
    if c["err"] - s["err"] > MAX_ERROR_DELTA:
        fails.append(f"canary errors +{(c['err'] - s['err']) * 100:.1f}pp vs stable")
    if c["p95"] > MAX_P95_SECONDS:
        fails.append(f"canary p95 {c['p95'] * 1000:.0f}ms > {MAX_P95_SECONDS * 1000:.0f}ms")
    if s["p95"] and c["p95"] > MAX_P95_RATIO * s["p95"]:
        fails.append(f"canary p95 {c['p95'] / s['p95']:.1f}x stable")
    return m, fails


def main():
    global PROM, INGRESS
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--fault-rate", default="0", help="demo only: inject 5xx errors into the canary")
    ap.add_argument("--step-seconds", type=int, default=30)
    ap.add_argument("--generate-load", action="store_true")
    ap.add_argument("--manifest", help="kustomization.yaml to update and commit after promotion")
    a = ap.parse_args()
    PROM = "http://" + sh("kubectl -n monitoring get svc prometheus -o jsonpath={.spec.clusterIP}") + ":9090"
    INGRESS = "http://" + sh("kubectl -n kube-system get svc traefik -o jsonpath={.spec.clusterIP}")
    window = f"{a.step_seconds}s"
    stop = threading.Event()
    if a.generate_load:
        load(stop)

    log(f"deploying canary {a.version} ({a.image}) with 1 replica, 0% traffic")
    sh(f"kubectl -n {NS} set image deployment/taskapi-canary taskapi={a.image}")
    sh(f"kubectl -n {NS} set env deployment/taskapi-canary APP_VERSION={a.version} FAULT_RATE={a.fault_rate}")
    sh(f"kubectl -n {NS} scale deployment/taskapi-canary --replicas=1")
    sh(f"kubectl -n {NS} rollout status deployment/taskapi-canary --timeout=120s")
    hdr = ("step", "canary req", "err%", "p95ms", "stable req", "err%", "p95ms")
    print("{:>5} | {:>10} {:>6} {:>6} | {:>10} {:>6} {:>6} | decision".format(*hdr))
    for w in STEPS:
        set_weights(w)
        time.sleep(a.step_seconds + 5)
        m, fails = analyse(window)
        c, s = m["canary"], m["stable"]
        row = (f"{w:>4}% | {c['req']:>10.0f} {c['err'] * 100:>6.2f} {c['p95'] * 1000:>6.1f} | "
               f"{s['req']:>10.0f} {s['err'] * 100:>6.2f} {s['p95'] * 1000:>6.1f} | ")
        if fails:
            print(row + "ROLLBACK", flush=True)
            set_weights(0)
            sh(f"kubectl -n {NS} scale deployment/taskapi-canary --replicas=0")
            log("ROLLED BACK: " + "; ".join(fails))
            log("all traffic restored to stable; canary scaled to 0")
            stop.set()
            sys.exit(1)
        print(row + "PASS", flush=True)

    log(f"all steps healthy -> promoting {a.version} to stable (rolling update, maxUnavailable=0)")
    sh(f"kubectl -n {NS} set image deployment/taskapi-stable taskapi={a.image}")
    sh(f"kubectl -n {NS} rollout status deployment/taskapi-stable --timeout=300s")
    set_weights(0)
    sh(f"kubectl -n {NS} scale deployment/taskapi-canary --replicas=0")
    log(f"PROMOTED: stable now runs {a.version}; canary scaled to 0")
    if a.manifest:  # keep Git as the source of truth, otherwise the next 'kubectl apply' reverts the release
        tag = a.image.rsplit(":", 1)[1]
        sh(f"sed -i 's/newName: taskapi, newTag: \"[^\"]*\"/newName: taskapi, newTag: \"{tag}\"/' {a.manifest}")
        sh(f"git add {a.manifest} && git commit -qm 'release: promote taskapi {a.version} to stable'")
        log(f"recorded release in Git: {a.manifest} -> {tag}")
    stop.set()


if __name__ == "__main__":
    main()
