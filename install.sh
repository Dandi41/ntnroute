#!/usr/bin/env bash
# NTnRoute.AI installer — engine + optional Hermes skills
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NTN_HOME="${NTN_HOME:-$HOME/.ntnroute}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
HERMES_SKILLS="${HERMES_SKILLS:-$HOME/.hermes/skills/networking}"

err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ok()  { printf 'OK: %s\n' "$*"; }

OS="$(uname -s)"
case "$OS" in
  MINGW*|MSYS*|CYGWIN*) WINDOWS=1 ;;
  *)                    WINDOWS=0 ;;
esac

# --- dependencies -----------------------------------------------------------
# Windows: jq is auto-provisioned into $NTN_HOME/bin (prepended to PATH by the
# engine). bash/ssh/timeout all ship with Git for Windows — that is the only
# prerequisite the user must install by hand.
if ! command -v jq >/dev/null 2>&1; then
  if [ "$WINDOWS" = 1 ] && command -v curl >/dev/null 2>&1; then
    mkdir -p "$NTN_HOME/bin"
    curl -L -sS -o "$NTN_HOME/bin/jq.exe" \
      https://github.com/jqlang/jq/releases/latest/download/jq-windows-amd64.exe \
      || err "failed to download jq — install it manually: https://jqlang.github.io/jq/download/"
    chmod +x "$NTN_HOME/bin/jq.exe" 2>/dev/null || true
    case ":$PATH:" in *":$NTN_HOME/bin:"*) ;; *) PATH="$NTN_HOME/bin:$PATH" ;; esac
    ok "jq installed automatically: $NTN_HOME/bin/jq.exe"
  else
    err "missing dependency: jq (install it, then re-run)"
  fi
fi
for dep in jq ssh; do
  command -v "$dep" >/dev/null 2>&1 || err "missing dependency: $dep (install it, then re-run)"
done
command -v timeout >/dev/null 2>&1 || command -v gtimeout >/dev/null 2>&1 \
  || err "missing dependency: timeout (GNU coreutils) — macOS: brew install coreutils — Windows: install Git for Windows"
ok "dependencies found (bash, jq, ssh)"

# --- engine ------------------------------------------------------------------
mkdir -p "$NTN_HOME" "$BIN_DIR"
install -m 700 "$REPO_DIR/ntn" "$NTN_HOME/ntn"
if ! ln -sfn "$NTN_HOME/ntn" "$BIN_DIR/ntn" 2>/dev/null || [ ! -e "$BIN_DIR/ntn" ]; then
  cp -f "$NTN_HOME/ntn" "$BIN_DIR/ntn" && ok "copy used instead of symlink (Windows/MSYS)"
fi
ok "engine installed: $NTN_HOME/ntn (symlinked as $BIN_DIR/ntn)"

# brand profiles: ship the default once, never overwrite user edits
if [ -f "$NTN_HOME/brands.json" ]; then
  ok "brands.json kept (user-managed): $NTN_HOME/brands.json"
else
  install -m 600 "$REPO_DIR/brands.json" "$NTN_HOME/brands.json"
  ok "brands.json installed: $NTN_HOME/brands.json"
fi

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *) echo "NOTE: $BIN_DIR is not in your PATH. Add it, e.g.:"
     echo "      echo 'export PATH=\"$BIN_DIR:\$PATH\"' >> ~/.bashrc" ;;
esac

# --- data dir ----------------------------------------------------------------
[ -f "$NTN_HOME/devices.json" ] || echo '[]' > "$NTN_HOME/devices.json"
chmod 600 "$NTN_HOME/devices.json"
mkdir -p "$NTN_HOME/backups"
chmod 700 "$NTN_HOME"
ok "data dir ready: $NTN_HOME (devices.json mode 600)"

# --- optional: Hermes skills --------------------------------------------------
if [ -d "$HOME/.hermes" ]; then
  mkdir -p "$HERMES_SKILLS"
  for s in ntnroute network-device-cli network-change-management network-troubleshooting network-security-audit; do
    rm -rf "$HERMES_SKILLS/$s"
    cp -r "$REPO_DIR/skills/$s" "$HERMES_SKILLS/$s"
  done
  ok "Hermes skills copied to $HERMES_SKILLS (restart Hermes to load them)"
else
  echo "NOTE: ~/.hermes not found — skipped skill install (engine works standalone)."
fi

echo
"$BIN_DIR/ntn" list || true
echo
echo "Add your first device:"
echo "  ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]"
echo "  e.g. ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123"
