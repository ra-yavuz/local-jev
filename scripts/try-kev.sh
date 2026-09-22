#!/usr/bin/env bash
set -euo pipefail

command_name="${1:-help}"
kev_dir="${KEV_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/local-jev/kev}"
kev_repo="${KEV_REPO:-https://github.com/jaredpalmer/kev.git}"
kev_run="${KEV_RUN:-jaredpalmer/kev-0.8b}"
kev_port="${KEV_PORT:-8009}"
kev_url="${KEV_URL:-http://127.0.0.1:${kev_port}/v1/systemone}"
local_jev_url="${LOCAL_JEV_URL:-http://127.0.0.1:8010/v1/systemone}"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

usage() {
  cat <<'EOF'
Usage:
  scripts/try-kev.sh install
  scripts/try-kev.sh serve
  scripts/try-kev.sh sample [url]
  scripts/try-kev.sh compare

Environment:
  KEV_DIR        Clone directory. Default: ~/.cache/local-jev/kev
  KEV_REPO       Kev repository URL. Default: https://github.com/jaredpalmer/kev.git
  KEV_RUN        Kev model or local checkpoint. Default: jaredpalmer/kev-0.8b
  KEV_PORT       Kev server port. Default: 8009
  KEV_URL        Full Kev /v1/systemone URL. Default: http://127.0.0.1:8009/v1/systemone
  LOCAL_JEV_URL  local-jev /v1/systemone URL. Default: http://127.0.0.1:8010/v1/systemone

Notes:
  Kev is a separate project. This helper clones it and runs its own setup.
  First runs can download large model files.
EOF
}

clone_or_update_kev() {
  require_command git
  if [ -d "$kev_dir/.git" ]; then
    git -C "$kev_dir" pull --ff-only
    return
  fi
  if [ -e "$kev_dir" ]; then
    echo "KEV_DIR exists but is not a git checkout: $kev_dir" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$kev_dir")"
  git clone "$kev_repo" "$kev_dir"
}

install_kev() {
  require_command uv
  clone_or_update_kev
  (
    cd "$kev_dir"
    uv sync --extra serve
  )
}

sample_payload() {
  cat <<'JSON'
{
  "state": "The build finished, unit tests passed, deployment health checks are green, and the canary error rate stayed below the rollback threshold.",
  "model": "kev-latest",
  "questions": {
    "route": {
      "type": "choice",
      "instructions": "Which action fits this release status?",
      "criteria": {
        "ship": "Proceed with the release",
        "watch": "Keep monitoring before release",
        "rollback": "Stop or roll back the release"
      }
    },
    "ready": {
      "type": "noul",
      "instructions": "Does the evidence support shipping?"
    },
    "risk": {
      "type": "score",
      "instructions": "How risky is the current release state?",
      "criteria": ["low risk", "medium risk", "high risk"]
    }
  }
}
JSON
}

send_sample() {
  require_command curl
  target_url="${1:-$kev_url}"
  sample_payload | curl -sS "$target_url" \
    -H 'content-type: application/json' \
    --data-binary @-
  printf '\n'
}

case "$command_name" in
  help|-h|--help)
    usage
    ;;
  install)
    install_kev
    ;;
  serve)
    install_kev
    (
      cd "$kev_dir"
      exec env KEV_DTYPE="${KEV_DTYPE:-bf16}" uv run --extra serve \
        python -m kev.serve --run "$kev_run" --port "$kev_port"
    )
    ;;
  sample)
    send_sample "${2:-$kev_url}"
    ;;
  compare)
    echo "local-jev: $local_jev_url"
    send_sample "$local_jev_url"
    echo "kev: $kev_url"
    send_sample "$kev_url"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
