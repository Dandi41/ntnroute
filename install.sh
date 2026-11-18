#!/usr/bin/env bash
# NTnRoute.AI beta-v1.0.2 installer — SSH + optional web/MCP + Hermes skills
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NTN_HOME="${NTN_HOME:-$HOME/.ntnroute}"
BIN_DIR="${BIN_DIR:-$HOME/.local/bin}"
HERMES_SKILLS="${HERMES_SKILLS:-$HOME/.hermes/skills/networking}"

err() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
ok()  { printf 'OK: %s\n' "$*"; }

# Parse and validate before any filesystem writes or optional downloads.
source "$REPO_DIR/install-web.sh"
ntn_web_parse "$@"
ntn_web_choose

# --- dependencies -----------------------------------------------------------
# Core dependencies must already be installed (including jq on Windows).
# Optional Playwright downloads require an explicit bundled selection.
for dep in jq ssh; do
  command -v "$dep" >/dev/null 2>&1 || err "missing dependency: $dep (install it, then re-run)"
done
command -v timeout >/dev/null 2>&1 || command -v gtimeout >/dev/null 2>&1 \
  || err "missing dependency: timeout (GNU coreutils) — macOS: brew install coreutils — Windows: install Git for Windows"
ok "dependencies found (bash, jq, ssh)"

# --- engine ------------------------------------------------------------------
if [ "$DRY_RUN" = 1 ]; then
  echo "DRY-RUN: install SSH engine and default brands (existing brands preserved)"
else
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
# devices.json is bootstrapped by the engine itself (canonical empty schema);
# creating it here with a different schema breaks every fresh install.
mkdir -p "$NTN_HOME/backups"
chmod 700 "$NTN_HOME"
ok "data dir ready: $NTN_HOME (devices.json mode 600)"

fi # non-dry-run engine/data install

# --- optional: Hermes skills --------------------------------------------------
# Manifest-based sync. The installer owns only what it installed, tracked in
# .ntn_manifest (path + sha256 at install time). Everything else in the
# installed tree — an agent-authored reference, a curator write — is preserved,
# never deleted. A repo-owned file that was edited locally: the repo version
# wins and the local copy is kept as <file>.local-<ts> (--force discards it).
SKILLS="ntnroute network-device-cli network-device-webui network-change-management network-troubleshooting network-security-audit"
MANIFEST="$HERMES_SKILLS/.ntn_manifest"
hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum "$1" | cut -d' ' -f1
  elif command -v shasum >/dev/null 2>&1; then shasum -a 256 "$1" | cut -d' ' -f1
  else openssl dgst -sha256 -r "$1" | cut -d' ' -f1; fi
}
if [ "$DRY_RUN" = 1 ]; then
  do_rm() { echo "DRY-RUN: rm -f $*"; }
  do_put() { echo "DRY-RUN: install $1 -> $2"; }
else
  do_rm() { rm -f "$@"; }
  do_put() { mkdir -p "$(dirname "$2")"; cp -f "$1" "$2"; }
fi

if [ -d "$HOME/.hermes" ]; then
  if [ "$DRY_RUN" = 0 ]; then mkdir -p "$HERMES_SKILLS"; fi
  HAVE_MANIFEST=0
  if [ -f "$MANIFEST" ]; then HAVE_MANIFEST=1; fi

  # Safety net: snapshot the current tree before touching it (keep the last 5).
  if [ "$DRY_RUN" = 0 ]; then
    snap="$NTN_HOME/backups/skills-$(date +%Y%m%d-%H%M%S).tar.gz"
    if tar -czf "$snap" -C "$HERMES_SKILLS" . 2>/dev/null; then
      ok "pre-install snapshot: $snap (last 5 kept)"
    else
      echo "NOTE: pre-install snapshot failed — continuing without it"
    fi
    old_snaps=$(ls -1t "$NTN_HOME"/backups/skills-*.tar.gz 2>/dev/null | tail -n +6 || true)
    for old in $old_snaps; do rm -f "$old"; done
  fi

  # 1. Prune repo-owned files the repo no longer ships (needs a manifest).
  if [ "$HAVE_MANIFEST" = 1 ]; then
    while read -r rel h; do
      [ -n "$rel" ] || continue
      if [ ! -e "$REPO_DIR/skills/$rel" ] && [ -f "$HERMES_SKILLS/$rel" ]; then
        echo "NOTE: removed stale repo-owned file: $rel"
        do_rm "$HERMES_SKILLS/$rel"
      fi
    done < "$MANIFEST"
  fi

  # 2. Install repo files with the four-way decision.
  OUT="$MANIFEST.new"
  if [ "$DRY_RUN" = 1 ]; then OUT=/dev/null; fi
  : > "$OUT" 2>/dev/null || true
  for s in $SKILLS; do
    src="$REPO_DIR/skills/$s"; dest="$HERMES_SKILLS/$s"
    [ -d "$src" ] || continue
    while IFS= read -r rel; do
      [ -n "$rel" ] || continue
      key="$s/$rel"
      h=$(hash_file "$src/$rel")
      if [ "$DRY_RUN" = 0 ]; then printf '%s %s\n' "$key" "$h" >> "$OUT"; fi
      d="$dest/$rel"
      if [ -e "$d" ] && [ "$HAVE_MANIFEST" = 1 ]; then
        old=$(awk -v k="$key" '$1==k{print $2; exit}' "$MANIFEST")
        cur=$(hash_file "$d")
        if [ -n "$old" ] && [ "$old" != "$cur" ]; then
          if [ "$FORCE" = 1 ]; then
            echo "WARNING: local edits discarded (--force): $key"
          else
            stamp2=$(date +%Y%m%d-%H%M%S)
            echo "WARNING: local edits saved: $key -> $rel.local-$stamp2"
            do_put "$d" "$d.local-$stamp2"
          fi
        fi
      fi
      do_put "$src/$rel" "$d"
    done < <(cd "$src" && find . -type f | sed 's|^\./||' | sort)
  done

  # 3. Report what the installer does not own and therefore never touches.
  if [ -d "$HERMES_SKILLS" ]; then
    ( cd "$HERMES_SKILLS" && find . -type f ! -name '.ntn_manifest*' ! -name '*.new' | sed 's|^\./||' ) \
      | while IFS= read -r rel; do
          [ -e "$REPO_DIR/skills/$rel" ] || echo "NOTE: preserved agent-authored file: $rel"
        done
  fi

  if [ "$DRY_RUN" = 1 ]; then
    echo "DRY-RUN: nothing written. Re-run without --dry-run to apply."
  else
    sort -u "$MANIFEST.new" > "$MANIFEST"
    rm -f "$MANIFEST.new"
    ok "Hermes skills synced to $HERMES_SKILLS (restart Hermes to load them)"
  fi
else
  echo "NOTE: ~/.hermes not found — skipped skill install (engine works standalone)."
fi

ntn_web_install

echo
if [ "$DRY_RUN" = 0 ]; then "$BIN_DIR/ntn" list || true; fi
echo
echo "Add your first device:"
echo "  ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]"
echo "  Supply credentials locally; never paste them into installer settings or logs."
