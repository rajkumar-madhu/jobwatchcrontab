#!/usr/bin/env bash
# R73 — register this Mac as the GitHub Actions runner that deploys JobWatch production.
#
#   deploy/runner/setup-mac.sh --token <registration token> [--labels wecrew-prod] [--name macbook-air]
#
# The registration token comes from GitHub: repo → Settings → Actions → Runners → New self-hosted
# runner → macOS (copy the token from the `./config.sh --token …` line; it expires in an hour).
# The runner is installed as a launchd service so it starts at login and the deploy job queues
# while the laptop is asleep (GitHub holds a queued job for 24 hours).
#
# What the runner needs on this machine: Docker Desktop running, kubectl pointing at the cluster
# (current context), helm, and kind if the cluster is kind. The deploy job checks all four.
set -euo pipefail
TOKEN= LABELS=wecrew-prod NAME=$(scutil --get ComputerName 2>/dev/null | tr ' ' '-' || hostname)
while [ $# -gt 0 ]; do case "$1" in --token) TOKEN=$2; shift 2;; --labels) LABELS=$2; shift 2;; --name) NAME=$2; shift 2;; *) echo "unknown flag $1" >&2; exit 2;; esac; done
: "${TOKEN:?--token <registration token from GitHub>}"
REPO_URL=https://github.com/rajkumar-madhu/jobwatchcrontab
DIR=$HOME/actions-runner-jobwatch
ARCH=$([ "$(uname -m)" = arm64 ] && echo arm64 || echo x64)
VER=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | python3 -c 'import sys,json;print(json.load(sys.stdin)["tag_name"].lstrip("v"))')
mkdir -p "$DIR" && cd "$DIR"
if [ ! -x ./config.sh ]; then
  echo "==> downloading actions-runner $VER ($ARCH)"
  curl -fsSL -o runner.tar.gz "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-osx-${ARCH}-${VER}.tar.gz"
  tar xzf runner.tar.gz && rm runner.tar.gz
fi
echo "==> registering as '$NAME' with labels self-hosted,macOS,$LABELS"
./config.sh --unattended --url "$REPO_URL" --token "$TOKEN" --name "$NAME" --labels "$LABELS" --work _work --replace
echo "==> installing as a launchd service (starts at login)"
./svc.sh install && ./svc.sh start && ./svc.sh status
echo
echo "Done. Check: $REPO_URL/settings/actions/runners should list '$NAME' as Idle."
echo "Keep Docker Desktop set to start at login, or the deploy job will fail its first check."
