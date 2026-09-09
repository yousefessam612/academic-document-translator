# Deploy the app to a Hugging Face Space (free, permanent public link, no card).
# Requires: HF_TOKEN environment variable (write permission, from
# https://huggingface.co/settings/tokens).
param(
    [string]$SpaceName = "academic-document-translator"
)

if (-not $env:HF_TOKEN) {
    Write-Error "Set HF_TOKEN first (create a write token at https://huggingface.co/settings/tokens)"
    exit 1
}

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# Make sure the hub client is available in the backend venv
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
& $py -m pip install --quiet --disable-pip-version-check huggingface_hub

# Pass values into the deployment script
$env:ADT_ROOT = $root
$env:ADT_SPACE = $SpaceName

$code = @'
import os
from pathlib import Path

from huggingface_hub import HfApi

root = Path(os.environ["ADT_ROOT"])
space = os.environ["ADT_SPACE"]

api = HfApi(token=os.environ["HF_TOKEN"])
who = api.whoami()
user = who["name"]
repo_id = f"{user}/{space}"
print(f"authenticated as: {user}")
print(f"space: https://huggingface.co/spaces/{repo_id}")

# Create the Docker Space (ok if it already exists)
api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker",
                private=False, exist_ok=True)

# ---- Secrets: read from the local .env (the file itself is NEVER uploaded) ----
def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

local_env = load_env(root / ".env")
for key in ("AGENTROUTER_API_KEY", "AGENTROUTER_BASE_URL", "AGENTROUTER_MODEL",
            "AGENTROUTER_REASONING_EFFORT"):
    value = local_env.get(key) or os.environ.get(key)
    if value:
        api.add_space_secret(repo_id=repo_id, key=key, value=value)
        print(f"secret set: {key}")
missing = [k for k in ("AGENTROUTER_API_KEY", "AGENTROUTER_MODEL")
           if not (local_env.get(k) or os.environ.get(k))]
if missing:
    print(f"WARNING: {missing} missing - add them in the Space settings.")

# ---- Upload ONLY application files (whitelist), never secrets/junk ----
result = api.upload_folder(
    repo_id=repo_id,
    repo_type="space",
    folder_path=str(root),
    allow_patterns=[
        "backend/app/**",
        "backend/tests/**",
        "backend/requirements.txt",
        "backend/pytest.ini",
        "backend/data/.gitkeep",
        "frontend/src/**",
        "frontend/public/**",
        "frontend/index.html",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/tsconfig*.json",
        "frontend/vite.config.ts",
        "frontend/eslint.config.*",
        "scripts/**",
        "docs/**",
        "storage/**/.gitkeep",
        "README.md",
        ".env.example",
        ".gitignore",
        ".dockerignore",
        "Dockerfile",
    ],
    ignore_patterns=[
        ".env",
        "**/__pycache__/**",
        "**/.pytest_cache/**",
        "backend/.venv/**",
        "backend/data/*.db*",
        "frontend/node_modules/**",
        "frontend/dist/**",
        "storage/uploads/**",
        "storage/outputs/**",
        "storage/temp/**",
        "storage/processed/**",
        "*.log",
    ],
    commit_message="Deploy Academic Document Translator",
)
print(f"upload complete: {result}")
print(f"APP URL: https://{user.replace('_', '-')}-{space.replace('_', '-')}.hf.space")
print("The Space is building now (takes a few minutes).")
'@
$code | & $py -
