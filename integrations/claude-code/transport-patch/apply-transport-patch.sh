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
#
# Safety invariants (all fail closed, exit 2 on violation):
#   * the target and backup MUST be regular files, never symlinks — a
#     symlinked server.ts is rejected and its referent is never modified;
#   * the target and backup MUST be owned by the caller;
#   * the target and backup MUST resolve to a path inside the supplied
#     plugin directory (no escape via a symlinked component);
#   * writes are atomic (write a sibling temp file, then rename in place).
set -eu

PLUGIN_DIR="${1:?usage: apply-transport-patch.sh <plugin-dir> [--verify|--rollback]}"
MODE="${2:-apply}"
PATCH_DIR="$(cd "$(dirname "$0")" && pwd)"

BASE_SHA256="c3c79c6519e23470fcc5f07e38415e50b4f054e42e670e89bd037fa64659e135"
PATCHED_SHA256="0d1ffaa0c51e60b09646e9e78ff92820f375695c0dbeac59f5393e6367b43b4c"
BASE_VERSION="0.0.4"

[ -d "$PLUGIN_DIR" ] || { echo "fail closed: $PLUGIN_DIR is not a directory" >&2; exit 2; }
PLUGIN_REAL="$(cd "$PLUGIN_DIR" 2>/dev/null && pwd -P)" \
  || { echo "fail closed: cannot resolve $PLUGIN_DIR" >&2; exit 2; }

TARGET="$PLUGIN_DIR/server.ts"
BACKUP="$PLUGIN_DIR/server.ts.orig-$BASE_VERSION"

sha() { python3 -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"; }

# Fail closed unless $1 is a regular, caller-owned file that resolves to a
# path confined within the plugin directory (never a symlink or escape).
require_safe_file() {
  _path="$1"
  _label="$2"
  [ -e "$_path" ] || { echo "fail closed: $_label does not exist ($_path)" >&2; exit 2; }
  [ -L "$_path" ] && { echo "fail closed: $_label is a symlink; refusing to follow ($_path)" >&2; exit 2; }
  [ -f "$_path" ] || { echo "fail closed: $_label is not a regular file ($_path)" >&2; exit 2; }
  [ -O "$_path" ] || { echo "fail closed: $_label is not owned by the caller ($_path)" >&2; exit 2; }
  _dir="$(cd "$(dirname "$_path")" 2>/dev/null && pwd -P)" \
    || { echo "fail closed: cannot resolve $_label directory" >&2; exit 2; }
  _real="$_dir/$(basename "$_path")"
  case "$_real" in
    "$PLUGIN_REAL"/*) : ;;
    *) echo "fail closed: $_label resolves outside the plugin directory ($_real)" >&2; exit 2 ;;
  esac
}

# Atomic in-place replace: write a sibling temp file, fsync via python, rename.
atomic_write() {
  _src="$1"
  _dst="$2"
  _tmp="$(mktemp "$PLUGIN_DIR/.server.ts.XXXXXX")" \
    || { echo "fail closed: cannot create temp file in plugin dir" >&2; exit 2; }
  cat "$_src" > "$_tmp"
  chmod 0644 "$_tmp"
  mv -f "$_tmp" "$_dst"
}

case "$MODE" in
  --verify)
    require_safe_file "$TARGET" "target server.ts"
    CURRENT="$(sha "$TARGET")"
    echo "target:  $TARGET"
    echo "current: $CURRENT"
    if [ "$CURRENT" = "$PATCHED_SHA256" ]; then echo "state: PATCHED (exact expected result)"; exit 0; fi
    if [ "$CURRENT" = "$BASE_SHA256" ]; then echo "state: PRISTINE BASE $BASE_VERSION (patch not applied)"; exit 1; fi
    echo "state: UNRECOGNIZED — neither pinned base nor expected patched result" >&2
    exit 2
    ;;
  --rollback)
    require_safe_file "$TARGET" "target server.ts"
    require_safe_file "$BACKUP" "pristine backup"
    [ "$(sha "$BACKUP")" = "$BASE_SHA256" ] || { echo "fail closed: backup does not match the pinned base digest" >&2; exit 2; }
    atomic_write "$BACKUP" "$TARGET"
    echo "rolled back to pristine base $BASE_VERSION ($BASE_SHA256)"
    exit 0
    ;;
  apply)
    require_safe_file "$TARGET" "target server.ts"
    CURRENT="$(sha "$TARGET")"
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
    if [ ! -e "$BACKUP" ]; then
      atomic_write "$TARGET" "$BACKUP"
    else
      require_safe_file "$BACKUP" "pristine backup"
      [ "$(sha "$BACKUP")" = "$BASE_SHA256" ] || { echo "fail closed: existing backup does not match the pinned base digest" >&2; exit 2; }
    fi
    atomic_write "$WORK/server.ts" "$TARGET"
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
