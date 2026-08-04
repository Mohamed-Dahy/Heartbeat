# A recipe for building the app into a self-contained image.

# ---------------------------------------------------------------------------
# Stage 1: build the React page.
#
# Node and node_modules are hundreds of megabytes, and they are needed only to
# TURN our source into plain HTML, CSS and JavaScript. Once that is done we do
# not need any of it.
#
# A "stage" is a throwaway container. We build here, then in stage 2 we copy out
# only the finished files and this entire stage is discarded. That is how the
# image stays small instead of ballooning past a gigabyte.
# ---------------------------------------------------------------------------
FROM node:22-slim AS frontend

WORKDIR /frontend

# Same layer-caching trick as requirements.txt below: copy the dependency list
# first and install, so editing a component does not reinstall React.
#
# npm ci (not npm install) installs exactly what package-lock.json says, and
# fails if the lockfile disagrees with package.json. That is what you want in a
# build: identical every time, no surprises.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: the actual image we ship.
#
# The starting point: a small official Linux image with Python 3.12 already on
# it. "slim" drops compilers and docs we do not need — about 130 MB instead of
# 1 GB. We pin 3.12 to match the version we develop on.
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: skip .pyc cache files. They only help on restart,
#   and a container is thrown away, so they are dead weight.
# PYTHONUNBUFFERED: print logs immediately instead of holding them in memory.
#   Without this, `docker logs` looks empty when something goes wrong.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Every command after this runs from /app inside the container, and relative
# paths are resolved from here. Without it we would be working in / and have
# to write out full paths everywhere.
WORKDIR /app

# Copy the dependency list on its own, and install BEFORE copying the code.
#
# Docker caches each step. If we copied everything at once, changing one line
# of Python would throw away the cache and reinstall FastAPI from scratch on
# every build. This way, the slow install step is only redone when
# requirements.txt actually changes.
#
# --no-cache-dir stops pip keeping a second copy of every package in the image.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now the code, which changes often and is cheap to copy.
COPY app/ ./app/

# Reach into stage 1 and take only the built page — no Node, no node_modules.
COPY --from=frontend /frontend/dist ./static

# By default everything in a container runs as root. If someone found a hole in
# our app, they would have full control of the container. This user can run the
# app and write to /data, and nothing else.
#
# /data is where the database will live, mounted from outside at run time.
RUN useradd --create-home --uid 1000 heartbeat \
    && mkdir -p /data \
    && chown -R heartbeat:heartbeat /app /data
USER heartbeat

ENV HEARTBEAT_DB=/data/heartbeat.db \
    HEARTBEAT_STATIC=/app/static

# Documentation only: it tells a reader which port to expect. It does not open
# anything by itself — that is what `-p 8000:8000` does when you run it.
EXPOSE 8000

# Docker keeps asking the app if it is alive. A crashed process is easy to spot,
# but a process that is still running while quietly serving errors is not — this
# catches that, and lets an orchestrator restart or replace the container.
#
# We call /api/history because it touches the web server AND the database
# without making any outbound calls. Pointing this at /api/status would mean
# hammering OpenAI and Anthropic every 30 seconds, forever, for no reason.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/history?limit=1').read()" || exit 1

# 0.0.0.0, not 127.0.0.1. Inside a container, 127.0.0.1 means "only this
# container can reach me" — your browser would get nothing. 0.0.0.0 means
# "accept connections from outside too".
#
# No --reload here: that is a development convenience that watches files and
# restarts. In production it wastes memory and can restart at a bad moment.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
