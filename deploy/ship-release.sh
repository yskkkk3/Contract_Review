#!/usr/bin/env bash
set -euo pipefail

: "${DEPLOY_HOST:?Missing DEPLOY_HOST}"
: "${DEPLOY_USER:?Missing DEPLOY_USER}"
: "${DEPLOY_SSH_KEY:?Missing DEPLOY_SSH_KEY}"
: "${DEPLOY_KNOWN_HOSTS:?Missing pinned DEPLOY_KNOWN_HOSTS}"
: "${DEPLOY_PATH:?Missing DEPLOY_PATH}"
: "${GITHUB_SHA:?Missing release SHA}"
[[ "$DEPLOY_HOST" =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]*$ ]]
[[ "$DEPLOY_USER" =~ ^[a-zA-Z0-9_][a-zA-Z0-9_-]*$ ]]
[[ "$DEPLOY_PATH" =~ ^/[a-zA-Z0-9_/-]+$ && "$DEPLOY_PATH" != / && "$DEPLOY_PATH" != *..* ]]
[[ "$GITHUB_SHA" =~ ^[a-f0-9]{40}$ ]]
[[ "${DEPLOY_PROJECT:-deploy}" =~ ^[a-z0-9][a-z0-9_-]*$ ]]

umask 077
mkdir -p "$RUNNER_TEMP/contract-review-ssh"
key_file="$RUNNER_TEMP/contract-review-ssh/key"
hosts_file="$RUNNER_TEMP/contract-review-ssh/known_hosts"
printf '%s\n' "$DEPLOY_SSH_KEY" > "$key_file"
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$hosts_file"
trap 'rm -f -- "$key_file"' EXIT
ssh_options=(-i "$key_file" -o BatchMode=yes -o ConnectTimeout=15 -o StrictHostKeyChecking=yes -o "UserKnownHostsFile=$hosts_file")
target="$DEPLOY_USER@$DEPLOY_HOST"
archive="$RUNNER_TEMP/contract-review-$GITHUB_SHA.tar.gz"
git archive --format=tar.gz --output="$archive" "$GITHUB_SHA"
ssh "${ssh_options[@]}" "$target" "mkdir -p -- '$DEPLOY_PATH/incoming'"
scp "${ssh_options[@]}" "$archive" "$target:$DEPLOY_PATH/incoming/$GITHUB_SHA.tar.gz"
ssh "${ssh_options[@]}" "$target" bash -s -- "$DEPLOY_PATH" "$GITHUB_SHA" "${DEPLOY_PROJECT:-deploy}" < deploy/remote-release.sh
