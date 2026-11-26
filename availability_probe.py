#!/usr/bin/env python3
"""User-facing availability probe through the ingress. Usage: availability_probe.py <seconds>"""
import collections, json, subprocess, sys, time, urllib.request
ip = subprocess.run("kubectl -n kube-system get svc traefik -o jsonpath={.spec.clusterIP}", shell=True, capture_output=True, text=True).stdout
end, ok, fail, versions = time.time() + float(sys.argv[1]), 0, 0, collections.Counter()
while time.time() < end:
    try:
        versions[json.loads(urllib.request.urlopen(f"http://{ip}/version", timeout=3).read())["version"]] += 1; ok += 1
    except Exception:
        fail += 1
    time.sleep(0.05)
print(f"probe: {ok + fail} requests, {fail} failed, availability {100 * ok / (ok + fail):.2f}%, served by {dict(versions)}")
