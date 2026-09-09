# Deployment Guide

The app ships as a self-contained Docker image (multi-stage: Node builds the
React frontend, Python 3.12 runs FastAPI + Tesseract OCR, FastAPI serves the
built SPA on one port). Default port: 8000 (overridable via `PORT`).

## Option A — Koyeb (recommended: free forever, usually NO credit card)

Free tier: 1 web service, 0.1 vCPU, 512 MB RAM, 2 GB SSD. Scales to zero
after ~1 hour of inactivity (cold start 10-60s), URL is permanent.

1. Open the deploy link (or click the badge in the README):
   https://app.koyeb.com/deploy?type=git&repository=github.com/yousefessam612/academic-document-translator&branch=master&builder=dockerfile
2. Sign up / log in **with GitHub** (no card for most users).
3. In the service configuration, add an environment variable:
   - `AGENTROUTER_API_KEY` = your AgentRouter key (required)
   - optional: `AGENTROUTER_MODEL` (default `glm-5.3`)
4. Create the service — Koyeb builds the Dockerfile and gives you a permanent
   URL like `https://academic-document-translator-xxxx.koyeb.app`.

If Koyeb asks you for a credit card (it sometimes does, depending on region),
use Option B instead.

## Option B — Back4App Containers (free, guaranteed NO credit card)

Free tier: 1 container, 0.25 CPU, 256 MB RAM. Sleeps when idle (like Render).

1. Go to https://www.back4app.com/container-as-a-service → Get Started.
2. Sign up with GitHub.
3. New deployment → connect the `academic-document-translator` GitHub repo.
4. Add environment variable `AGENTROUTER_API_KEY` (required).
5. Deploy — you get a `*.back4app.app` URL.

Note: 256 MB RAM is enough for text-based PDFs/DOCX/TXT, but heavy OCR of
large scanned PDFs may exceed it. Prefer Koyeb when available.

## Option C — Render (free 750 hrs/month, but requires a credit card)

https://render.com/deploy?repo=https://github.com/yousefessam612/academic-document-translator

## Free-tier limitations (all options)

- **Ephemeral disk**: uploaded files, the SQLite database, and generated
  documents are wiped when the container restarts (after sleeping or
  redeploying). The terminology dictionary re-seeds automatically; use
  Terminology → Export CSV to back up custom terms. Translate and download
  your DOCX within the same session.
- **Public link**: anyone with the link can use the app and consume API
  credits — don't share it publicly.
- **Cold starts**: the first visit after idle takes 10-60 seconds to wake.
- The API key is injected as a runtime environment variable — it is never
  stored in the image or the git repo.
