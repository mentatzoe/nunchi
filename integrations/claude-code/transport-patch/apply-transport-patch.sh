#!/bin/sh
# apply-transport-patch.sh — fail-closed installer for the Nunchi Claude
# Discord transport patches.
#
# Usage:
#   apply-transport-patch.sh <plugin-dir>            apply both patches
#   apply-transport-patch.sh <plugin-dir> --verify   report state, change nothing
#   apply-transport-patch.sh <plugin-dir> --rollback restore the pristine base
#
# The patches are bound to ONE exact upstream base (claude-plugins-official
# discord plugin 0.0.4, server.ts). If the file present on disk is neither
# that exact pristine base nor the exact expected patched result, this script
# refuses to touch it (exit 2). It never fuzzes onto an unreviewed upstream.
set -eu

PLUGIN_DIR="${1:?usage: apply-transport-patch.sh <plugin-dir> [--verify|--rollback]}"
MODE="${2:-apply}"
PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"

BASE_SHA256="c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135"
PATCHED_SHA256="e26b6d2316413f2fb886a54346364e44c1c29dbffc6136dbfeb357b69198f115"
BASE_VERSION="0.0.4"

TARGET="$PLUGIN_DIR/server.ts"
BACKUP="$PLUGIN_DIR/server.ts.orig-$BASE_VERSION"

sha() { python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"; }

[ -f "$TARGET" ] || { echo "fail closed: $TARGET does not exist" >&2; exit 2; }
CURRENT="$(sha "$TARGET")"

case "$MODE" in
  --verify)
    echo "target:  $TARGET"
    echo "current: $CURRENT"
    if [ "$CURRENT" = "$PATCHED_SHA256" ]; then echo "state: PATCHED (exact expected result)"; exit 0; fi
    if [ "$CURRENT" = "$BASE_SHA256" ]; then echo "state: PRISTINE BASE $BASE_VERSION (patch not applied)"; exit 1; fi
    echo "state: UNRECOGNIZED — neither pinned base nor expected patched result" >&2
    exit 2
    ;;
  --rollback)
    [ -f "$BACKUP" ] || { echo "fail closed: no pristine backup at $BACKUP" >&2; exit 2; }
    [ "$(sha "$BACKUP")" = "$BASE_SHA256" ] || { echo "fail closed: backup does not match the pinned base digest" >&2; exit 2; }
    cp "$BACKUP" "$TARGET"
    echo "rolled back to pristine base $BASE_VERSION ($BASE_SHA256)"
    exit 0
    ;;
  apply)
    if [ "$CURRENT" = "$PATCHED_SHA256" ]; then
      echo "already patched (exact expected result); nothing to do"
      exit 0
    fi
    if [ "$CURRENT" != "$BASE_SHA256" ]; then
      echo "fail closed: $TARGET is neither the pinned $BASE_VERSION base nor the expected patched result." >&2
      echo "  current: $CURRENT" >&2
      echo "  pinned base: $BASE_SHA256" >&2
      echo "The upstream plugin has changed; re-review and rebase the patches before installing." >&2
      exit 2
    fi
    WORK="$(mktemp -d)"
    trap 'rm -rf "$WORK"' EXIT
    cp "$TARGET" "$WORK/server.ts"
    ( cd "$WORK" \
      && git apply --check "$PATCH_DIR/0001-allow-bot-messages-allowfrom.patch" \
      && git apply "$PATCH_DIR/0001-allow-bot-messages-allowfrom.patch" \
      && git apply --check "$PATCH_DIR/0002-native-fact-sidecar.patch" \
      && git apply "$PATCH_DIR/0002-native-fact-sidecar.patch" ) \
      || { echo "fail closed: patches did not apply exactly" >&2; exit 2; }
    RESULT="$(sha "$WORK/server.ts")"
    [ "$RESULT" = "$PATCHED_SHA256" ] || { echo "fail closed: patched result digest mismatch ($RESULT)" >&2; exit 2; }
    [ -f "$BACKUP" ] || cp "$TARGET" "$BACKUP"
    cp "$WORK/server.ts" "$TARGET"
    echo "patched: $TARGET"
    echo "base:    $BASE_SHA256 (backup at $BACKUP)"
    echo "result:  $PATCHED_SHA256"
    echo "restart the Claude Code session so the plugin process reloads."
    exit 0
    ;;
  *)
    echo "unknown mode: $MODE" >&2
    exit 2
    ;;
esac
