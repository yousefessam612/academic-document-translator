# Deploy the app to a Hugging Face Space (free, permanent public link).
# Requires: HF_TOKEN environment variable (write permission).
param(
    [Parameter(Mandatory = $true)]
    [string]$SpaceName = "academic-document-translator"
)

if (-not $env:HF_TOKEN) {
    Write-Error "Set HF_TOKEN first (create a write token at https://huggingface.co/settings/tokens)"
    exit 1
}

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# Install the hub client into the backend venv if missing
$py = Join-Path $root "backend\.venv\Scripts\python.exe"
& $py -m pip install --quiet huggingface_hub

# Deploy via the hub library
$code = @"
import os, sys
from huggingface_hub import HfApi

api = HfApi(token=os.environ["HF_TOKEN"])
who = api.whoami()
user = who["name"]
repo_id = f"{user}/$SpaceName"
print(f"authenticated as: {user}")

# Create the Docker Space (ok if it already exists)
try:
    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", private=False, exist_ok=True)
    print(f"space ready: https://huggingface.co/spaces/{repo_id}")
except Exception as e:
    print(f"create_repo: {e}"); sys.exit(1)

# Push secrets (never stored in git)
for key in ("AGENTROUTER_API_KEY", "AGENTROUTER_BASE_URL", "AGENTROUTER_MODEL"):
    value = os.environ.get(key)
    if value:
        api.add_space_secret(repo_id=repo_id, key=key, value=value)
        print(f"secret set: {key}")
missing = [k for k in ("AGENTROUTER_API_KEY", "AGENTROUTER_MODEL") if not os.environ.get(k)]
if missing:
    print(f"WARNING: {missing} not set in this environment - add them in the Space settings.")

# Upload the repo (respects .gitignore, uploads from the working tree)
api.upload_folder(
    repo_id=repo_id,
    repo_type="space",
    folder_path=r"$root",
    commit_message="Deploy Academic Document Translator",
)
print("upload complete - the Space is building now (takes a few minutes)")
print(f"APP URL: https://{user.replace('_', '-')}-{repo_id.split('/')[-1].replace('_', '-')}.hf.space"
"@
$env:HF_TOKEN = $env:HF_TOKEN
$code | & $py -
