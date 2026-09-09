# Deployment Guide

The app runs anywhere that can run the provided `Dockerfile` (multi-stage:
Node builds the React frontend, Python 3.12 runs FastAPI + Tesseract OCR,
FastAPI serves the built SPA on one port).

## Option A — Hugging Face Spaces (recommended, free)

Free CPU tier: 2 vCPU / 16 GB RAM. The Space stays up 48h of inactivity
before sleeping; waking takes ~30s on the next visit and the public link never
changes.

1. Create a free account at https://huggingface.co (you can sign in with GitHub).
2. Settings → Access Tokens → create a token with **write** permission.
3. Create a Docker Space (or let the deploy script create it):
   ```powershell
   .\backend\.venv\Scripts\pip.exe install huggingface_hub
   $env:HF_TOKEN = "hf_xxx"
   .\scripts\deploy_hf.ps1
   ```
   The script creates the Space, sets `AGENTROUTER_API_KEY` etc. as Space
   secrets, and pushes the repo.
4. Your permanent link: `https://<username>-academic-document-translator.hf.space`

**Secrets** (Space → Settings → Variables and secrets): `AGENTROUTER_API_KEY`,
`AGENTROUTER_BASE_URL`, `AGENTROUTER_MODEL`. Everything else has working defaults.

## Option B — Render (free tier)

1. Push the repo to GitHub (already done).
2. Open: https://render.com/deploy?repo=https://github.com/yousefessam612/academic-document-translator
3. Log in with GitHub, paste `AGENTROUTER_API_KEY` when prompted, deploy.
4. Link: `https://academic-document-translator.onrender.com`

Free Render services sleep after 15 min of inactivity (cold start ~1 min) and
have 512 MB RAM.

## Free-tier limitations (both options)

- **Ephemeral disk**: uploaded files, the SQLite database, and generated
  documents are wiped when the container restarts (after sleeping or
  redeploying). The terminology dictionary re-seeds automatically; use
  Terminology → Export CSV to back up custom terms. For persistent storage use
  HF persistent storage (~$5/mo) or a paid Render disk.
- **Public link**: anyone with the link can use the app and consume API
  credits. On Hugging Face you can flip the Space to *Private* in Settings
  (then only you can open it with your HF login).
- The API key is injected as a runtime secret — it is never stored in the
  image or the git repo.
