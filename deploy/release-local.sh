#!/usr/bin/env bash
# R72 — deploy from a workstation to a cluster you already reach with kubectl, without the GitHub
# deploy workflow. Builds the api and web images for the given domain, pushes them (or loads them
# into kind), runs the migrate hook and `helm upgrade`, then the smoke test.
#
#   deploy/release-local.sh --domain jobwatch.wecrew.in --ingest-domain ingest.jobwatch.wecrew.in \
#       --context <kube-context> [--namespace jobwatch] [--release jobwatch] \
#       [--registry ghcr.io/<owner>] | [--kind <cluster-name>] \
#       [--values deploy/environments/production.yaml] [--secret-values /path/secret-values.yaml] \
#       [--tag v0.72.0]
#
# secret-values.yaml holds what the GitHub Environment would: see the header of
# .github/workflows/deploy.yml (DATABASE_URL, migration.databaseUrl, migration.appDbPassword,
# SECRET_ENCRYPTION_KEY, Keycloak client secrets …). It is read by helm only and never printed.
#
# Nothing here is destructive: helm upgrade is reversible with `helm rollback`; migrations are not
# (take a DB backup first — docs/DEPLOY.md, Rollback).
set -euo pipefail
cd "$(dirname "$0")/.."

DOMAIN= INGEST= CONTEXT= NS=jobwatch REL=jobwatch REGISTRY= KIND= VALUES=deploy/environments/production.yaml SECRETS= TAG=
while [ $# -gt 0 ]; do
  case "$1" in
    --domain) DOMAIN=$2; shift 2;; --ingest-domain) INGEST=$2; shift 2;; --context) CONTEXT=$2; shift 2;;
    --namespace) NS=$2; shift 2;; --release) REL=$2; shift 2;; --registry) REGISTRY=$2; shift 2;; --kind) KIND=$2; shift 2;;
    --values) VALUES=$2; shift 2;; --secret-values) SECRETS=$2; shift 2;; --tag) TAG=$2; shift 2;;
    *) echo "unknown flag $1" >&2; exit 2;;
  esac
done
: "${DOMAIN:?--domain}"; : "${INGEST:?--ingest-domain}"; : "${CONTEXT:?--context}"
[ -n "$REGISTRY" ] || [ -n "$KIND" ] || { echo "need --registry <ghcr.io/owner> or --kind <cluster>" >&2; exit 2; }
TAG=${TAG:-$(git describe --tags --always 2>/dev/null || date +%Y%m%d%H%M)}
PREFIX=${REGISTRY:-jobwatch-local}
API_IMG=$PREFIX/jobwatch-api:$TAG; WEB_IMG=$PREFIX/jobwatch-web:$TAG

for t in docker kubectl helm; do command -v $t >/dev/null || { echo "$t not installed" >&2; exit 2; }; done
kubectl config use-context "$CONTEXT" >/dev/null
echo "==> context $CONTEXT · namespace $NS · release $REL · tag $TAG"
echo "==> current release:"; helm -n "$NS" history "$REL" --max 3 2>/dev/null || echo "   (none — first install)"

echo "==> building images"
docker build -q -f infra/docker/Dockerfile.api -t "$API_IMG" .
docker build -q -f infra/docker/Dockerfile.web -t "$WEB_IMG" \
  --build-arg "NEXT_PUBLIC_API_URL=https://$DOMAIN" --build-arg "NEXT_PUBLIC_INGEST_URL=https://$INGEST" \
  --build-arg "NEXT_PUBLIC_BOOKING_URL=${BOOKING_URL:-}" .     # R74: optional Cal.com/Calendly link for "talk to a human"

if [ -n "$KIND" ]; then
  echo "==> loading images into kind cluster $KIND"
  kind load docker-image "$API_IMG" "$WEB_IMG" --name "$KIND"
else
  echo "==> pushing images to $REGISTRY"
  docker push -q "$API_IMG"; docker push -q "$WEB_IMG"
fi

echo "==> helm upgrade (runs the migrate hook first: alembic upgrade head as the DB owner)"
helm upgrade --install "$REL" infra/helm/cronsentinel --namespace "$NS" --create-namespace \
  -f "$VALUES" ${SECRETS:+-f "$SECRETS"} \
  --set-string "image.api=$API_IMG" --set-string "image.web=$WEB_IMG" \
  ${KIND:+--set-string imagePullPolicy=IfNotPresent} \
  --set-string "domain=$DOMAIN" --set-string "ingestDomain=$INGEST" \
  --set-string "env.API_PUBLIC_URL=https://$DOMAIN" --set-string "env.WEB_PUBLIC_URL=https://$DOMAIN" \
  --set-string "env.INGEST_PUBLIC_URL=https://$INGEST" \
  --set-string "env.AGENT_DOWNLOAD_BASE=https://github.com/rajkumar-madhu/jobwatchcrontab/releases/download" \
  --set-string "env.AGENT_VERSION=$TAG" \
  --wait --timeout 15m

echo "==> smoke"
if deploy/smoke.sh "https://$DOMAIN" "https://$INGEST"; then
  echo "==> deployed $TAG to https://$DOMAIN"
else
  echo "==> smoke failed — rolling the application back (the database stays migrated)"; helm -n "$NS" rollback "$REL"; exit 1
fi
