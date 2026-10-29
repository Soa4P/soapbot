# syntax=docker/dockerfile:1.7
#
# Hardened image for the bot.
#
# The image encodes the deployment-layer controls that `soapbot doctor` can only
# *report* on: a non-root uid, no capabilities, a read-only root filesystem (set in
# compose, not here), and secrets delivered as files rather than environment
# variables.
#
# Everything here is a default that fails closed. Where a setting could be either
# convenient or safe, it is safe, and the compose file documents how to relax it.

# ---------------------------------------------------------------- build stage
FROM python:3.12-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Copy only what the build needs, so a change to tests/docs does not bust the layer.
COPY pyproject.toml README.md ./
COPY src ./src

# Build a wheel, install into a throwaway prefix. Keeps build tooling out of the
# runtime image entirely — no pip, no setuptools, nothing to exploit post-compromise.
RUN pip install --upgrade pip build \
 && python -m build --wheel --outdir /dist \
 && pip install --prefix=/install /dist/*.whl

# -------------------------------------------------------------- runtime stage
FROM python:3.12-slim AS runtime

# A fixed high uid/gid. Not 1000: that collides with the default first user on most
# hosts, which invites sloppy bind-mount ownership as a "fix".
ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    # Never write .pyc into a read-only rootfs; the write attempt alone slows startup
    # and fills logs with permission errors that look like a broken deploy.
    SOAPBOT_DATA_DIR=/data \
    # The panel's settings page (page 12) writes this file. The default is `.env` in the
    # working directory, and here the working directory is on a read-only rootfs — so
    # every save would fail with a permission error while the rest of the panel looked
    # fine. Pointing it at the data volume makes the write land somewhere that survives
    # a restart, which is also what makes "restart to apply" true rather than decorative.
    SOAPBOT_ENV_FILE=/data/.env

# Runtime deps only: tini for correct signal handling (PID 1 must reap zombies, or
# plugin worker processes accumulate as unreaped children and eventually fail fork).
RUN apt-get update \
 && apt-get install -y --no-install-recommends tini \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid "${APP_GID}" app \
 && useradd --uid "${APP_UID}" --gid "${APP_GID}" --create-home --shell /usr/sbin/nologin app

COPY --from=build /install /usr/local

# Application code owned by root and read-only to the app user: a compromised plugin
# cannot rewrite the host's own source to persist across restarts.
COPY --chown=root:root src /app/src
ENV PYTHONPATH=/app/src

# Configuration (providers / adapters / personas). Copied in so the image contains the
# same defaults as the repository; compose mounts the operator's directory over it,
# read-only. Omitting this step was the reason a containerised bot started with no
# adapters and no persona while the checkout worked — the config path simply did not
# exist inside the image.
COPY --chown=root:root config /app/config
ENV SOAPBOT_CONFIG_DIR=/app/config

# Data is the only writable path, and it is a volume.
RUN mkdir -p /data && chown "${APP_UID}:${APP_GID}" /data
VOLUME ["/data"]

USER ${APP_UID}:${APP_GID}
WORKDIR /app

EXPOSE 6185

# Tini as PID 1: forwards SIGTERM to the app and reaps orphaned plugin workers.
ENTRYPOINT ["/usr/bin/tini", "--"]
# `--host 0.0.0.0`: a port mapping reaches the container's eth0, so binding the
# container's loopback would make the mapping useless. The host-side bind is what
# restricts exposure — compose publishes on 127.0.0.1 only.
CMD ["python", "-m", "soapbot.cli", "start", "--host", "0.0.0.0", "--port", "6185"]
