#!/usr/bin/env bash
set -euo pipefail

root="${1:?Missing app root}"
revision="${2:?Missing release SHA}"
project="${3:-deploy}"
[[ "$root" =~ ^/[a-zA-Z0-9_/-]+$ && "$root" != / && "$root" != *..* ]]
[[ "$revision" =~ ^[a-f0-9]{40}$ ]]
[[ "$project" =~ ^[a-z0-9][a-z0-9_-]*$ ]]
test -f "$root/shared/.env"
if [[ -e "$root/current" && ! -L "$root/current" ]]; then
    echo "current must be a release symlink" >&2
    exit 1
fi
command -v flock >/dev/null
mkdir -p "$root/releases"
exec 9> "$root/deployment.lock"
flock -n 9 || { echo "Another deployment is running" >&2; exit 1; }
release="$root/releases/$revision"
mkdir -p "$release"
tar -xzf "$root/incoming/$revision.tar.gz" -C "$release"
ln -sfn "$root/shared/.env" "$release/.env"
previous="$(readlink -f "$root/current" || true)"
compose=(docker compose --project-name "$project" --env-file "$root/shared/.env" -f "$release/deploy/docker-compose.yml")
"${compose[@]}" config --quiet
if ! "${compose[@]}" up -d --build --wait --wait-timeout 300; then
    echo "Deployment failed; restoring previous release" >&2
    if [[ -n "$previous" && -f "$previous/deploy/docker-compose.yml" ]]; then
        docker compose --project-name "$project" --env-file "$root/shared/.env" -f "$previous/deploy/docker-compose.yml" up -d --build --wait --wait-timeout 300
    fi
    exit 1
fi
ln -sfn "$release" "$root/current"
echo "Deployed revision $revision"
