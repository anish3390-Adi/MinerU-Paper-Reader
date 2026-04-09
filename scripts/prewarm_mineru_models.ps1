$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:MINERU_MODEL_SOURCE = "modelscope"

$pythonCode = @'
import json
import os
from pathlib import Path

from modelscope import snapshot_download

repo_id = "OpenDataLab/PDF-Extract-Kit-1.0"
model_root = snapshot_download(repo_id)
print(model_root)

config_path = Path.home() / "mineru.json"
if config_path.exists():
    config = json.loads(config_path.read_text(encoding="utf-8"))
else:
    config = {}

models_dir = config.get("models-dir", {})
models_dir["pipeline"] = model_root
config["models-dir"] = models_dir
config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

print(f"Configured pipeline model root: {model_root}")
print(f"Updated config: {config_path}")
'@

$pythonCode | python -
