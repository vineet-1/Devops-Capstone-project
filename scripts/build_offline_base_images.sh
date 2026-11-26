#!/usr/bin/env bash
# Offline lab only: build base images from the Ubuntu package mirror when no container registry is reachable.
# (Outside the lab, the Dockerfiles use the official python:3.12-slim and postgres:16-alpine images.)
set -euo pipefail
ROOT=/opt/rootfs
debootstrap --variant=minbase --include=python3,ca-certificates noble $ROOT http://archive.ubuntu.com/ubuntu/
echo "deb http://archive.ubuntu.com/ubuntu noble main universe" > $ROOT/etc/apt/sources.list
cp /etc/resolv.conf $ROOT/etc/resolv.conf
for d in proc sys dev; do mount --bind /$d $ROOT/$d; done
chroot $ROOT bash -c "apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends python3.12-venv python3-pip && apt-get clean && rm -rf /var/lib/apt/lists/*"
for d in proc sys dev; do umount $ROOT/$d; done
tar -C $ROOT -c . | docker import -c 'ENV LANG=C.UTF-8 PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' - capstone/ubuntu-python:24.04
cp -a $ROOT /opt/pgroot
for d in proc sys dev; do mount --bind /$d /opt/pgroot/$d; done
chroot /opt/pgroot bash -c "apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends postgresql-16 postgresql-client-16 && apt-get clean && rm -rf /var/lib/apt/lists/*"
for d in proc sys dev; do umount /opt/pgroot/$d; done
tar -C /opt/pgroot -c . | docker import -c 'ENV LANG=C.UTF-8 PATH=/usr/lib/postgresql/16/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin' - capstone/ubuntu-postgres:16-base
# Python wheels for the app image (installed with --no-index inside docker build)
pip download -r requirements.txt -d vendor --python-version 3.12 --platform manylinux2014_x86_64 \
  --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 --only-binary=:all: --implementation cp
