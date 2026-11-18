#!/usr/bin/env bash
# Optional installer support. Source from install.sh; never run providers here.
ntn_web_parse() {
  DRY_RUN=0; FORCE=0; NON_INTERACTIVE=0
  WEB_CHOICE=""; MCP_CHOICE=""; WEB_ADAPTER=""; MCP_ADAPTER=""
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --dry-run) DRY_RUN=1 ;;
      --force) FORCE=1 ;;
      --non-interactive) NON_INTERACTIVE=1 ;;
      --web|--mcp|--web-adapter|--mcp-adapter)
        [ "$#" -ge 2 ] || err "missing value for $1"
        case "$1" in
          --web) WEB_CHOICE="$2" ;;
          --mcp) MCP_CHOICE="$2" ;;
          --web-adapter) WEB_ADAPTER="$2" ;;
          --mcp-adapter) MCP_ADAPTER="$2" ;;
        esac
        shift ;;
      --help|-h)
        cat <<'HELP'
Usage: bash install.sh [--dry-run] [--force] [--non-interactive]
  --web existing|bundled|skip    Existing adapter, bundled Playwright, or skip
  --web-adapter /absolute/path  Trusted ntn-web-provider/1 executable (no args)
  --mcp existing|bundled|skip    Existing MCP executable, bundled stdio, or skip
  --mcp-adapter /absolute/path  Trusted stdio MCP server for NTnRoute web tools
Noninteractive input defaults to skip. Only --web bundled downloads packages
and Chromium into a private venv/cache. No global pip or client config changes.
Existing browser adapters MUST implement web/PROVIDER.md, not arbitrary browser
CLIs. Existing MCP adapters MUST implement JSON-RPC MCP stdio and expose the
NTnRoute inspect/plan/apply/rollback approval contract; never auto-approve.
Adapters are trusted executables, not shell strings. Secrets belong in inventory,
never adapter paths or settings. Profiles are user-managed and not overwritten.
HELP
        exit 0 ;;
      *) err "unknown option: $1 (see --help)" ;;
    esac
    shift
  done
}

ntn_web_choose() {
  if [ "$NON_INTERACTIVE" = 0 ] && [ -t 0 ]; then
    printf '%s\n' 'Existing providers require trusted executable adapters, not arbitrary browser/MCP tools.'
    printf '%s\n' 'Browser: ntn-web-provider/1 (web/PROVIDER.md). MCP: NTnRoute stdio tools with explicit approval gates.'
    if [ -z "$WEB_CHOICE" ]; then
      printf 'Browser backend [existing / bundled Playwright (downloads) / skip] (skip): '
      read -r WEB_CHOICE || true
    fi
    if [ "$WEB_CHOICE" = existing ] && [ -z "$WEB_ADAPTER" ]; then
      printf 'Absolute executable implementing ntn-web-provider/1 (see web/PROVIDER.md): '
      read -r WEB_ADAPTER || true
    fi
    if [ -z "$MCP_CHOICE" ]; then
      printf 'MCP integration [existing NTnRoute stdio adapter / bundled / skip] (skip): '
      read -r MCP_CHOICE || true
    fi
    if [ "$MCP_CHOICE" = existing ] && [ -z "$MCP_ADAPTER" ]; then
      printf 'Absolute executable implementing NTnRoute MCP stdio tools (no arbitrary MCP compatibility): '
      read -r MCP_ADAPTER || true
    fi
  fi
  WEB_CHOICE="${WEB_CHOICE:-skip}"; MCP_CHOICE="${MCP_CHOICE:-skip}"
  case "$WEB_CHOICE" in existing|bundled|skip) ;; *) err "invalid --web choice" ;; esac
  case "$MCP_CHOICE" in existing|bundled|skip) ;; *) err "invalid --mcp choice" ;; esac
  ntn_web_adapter "$WEB_CHOICE" "$WEB_ADAPTER" --web-adapter
  ntn_web_adapter "$MCP_CHOICE" "$MCP_ADAPTER" --mcp-adapter
  # Snapshot and validate before install.sh performs any writes. Never evaluate
  # settings as shell input or include parser diagnostics (possibly secrets).
  WEB_SETTINGS_JSON='{}'
  if { [ "$WEB_CHOICE" != skip ] || [ "$MCP_CHOICE" != skip ]; } && \
      { [ -e "$NTN_HOME/web-settings.json" ] || [ -L "$NTN_HOME/web-settings.json" ]; }; then
    [ -f "$NTN_HOME/web-settings.json" ] || err 'invalid existing web settings'
    WEB_SETTINGS_JSON="$(jq -cse '
      def component($protocol):
        type == "object" and
        (if has("provider") then (.provider | IN("existing", "bundled", "skip")) else true end) and
        (if has("executable") then (.executable | type == "string") else true end) and
        (if has("protocol") then .protocol == $protocol else true end);
      if length != 1 then error("invalid") else .[0] end |
      if type == "object" and .version == 1 and
        (if has("browser") then (.browser | component("ntn-web-provider/1")) else true end) and
        (if has("mcp") then (.mcp | component("mcp-stdio")) else true end) and
        ( . as $settings | all(["python", "profiles_dir", "state_dir", "browsers_path"][];
          . as $key | $settings | if has($key) then (.[$key] | type == "string") else true end))
      then . else error("invalid") end
    ' "$NTN_HOME/web-settings.json" 2>/dev/null)" || err 'invalid existing web settings'
  fi
  if [ "$WEB_CHOICE" != skip ] || [ "$MCP_CHOICE" = bundled ]; then
    [ -d "$REPO_DIR/web" ] || err "bundled web tree missing from source"
    command -v python3 >/dev/null 2>&1 || err "Python 3.10+ required for web backend"
  fi
}

ntn_web_adapter() {
  if [ "$1" = existing ]; then
    case "$2" in /*) ;; *) err "$3 requires an absolute executable path (no arguments)" ;; esac
    [ -f "$2" ] && [ -x "$2" ] || err "$3 must be an executable file"
  elif [ -n "$2" ]; then
    err "$3 requires the corresponding existing choice"
  fi
}

ntn_web_install() {
  if [ "$WEB_CHOICE" = skip ] && [ "$MCP_CHOICE" = skip ]; then
    ok 'optional browser and MCP skipped (existing settings untouched)'
    return
  fi
  if [ "$DRY_RUN" = 1 ]; then
    printf 'DRY-RUN: browser=%s MCP=%s; settings at %s/web-settings.json; no writes or downloads\n' "$WEB_CHOICE" "$MCP_CHOICE" "$NTN_HOME"
    return
  fi
  local python_bin="" browser_dir="$NTN_HOME/browsers" rel src dest settings_tmp
  if [ "$WEB_CHOICE" != skip ] || [ "$MCP_CHOICE" = bundled ]; then
    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
      || err 'Python 3.10+ required for web backend'
    python_bin="$(command -v python3)"
    mkdir -p "$NTN_HOME/web"
    while IFS= read -r -d '' src; do
      rel="${src#"$REPO_DIR/web/"}"
      case "$rel" in __pycache__/*|*/__pycache__/*|*.pyc) continue ;; esac
      dest="$NTN_HOME/web/$rel"
      # Reviewed/imported profiles are user-owned, including bundled examples.
      case "$rel" in profiles/*) [ ! -e "$dest" ] || continue ;; esac
      mkdir -p "$(dirname "$dest")"
      install -m 600 "$src" "$dest"
    done < <(find "$REPO_DIR/web" -type f -print0)
  fi
  mkdir -p "$NTN_HOME/web/profiles" "$NTN_HOME/web-state"
  chmod 700 "$NTN_HOME/web-state"
  if [ "$WEB_CHOICE" = bundled ]; then
    python3 -m venv "$NTN_HOME/web-venv" || err 'could not create private venv; install Python venv support'
    python_bin="$NTN_HOME/web-venv/bin/python"
    [ -x "$python_bin" ] || python_bin="$NTN_HOME/web-venv/Scripts/python.exe"
    "$python_bin" -m pip install playwright || err 'Playwright install failed'
    PLAYWRIGHT_BROWSERS_PATH="$browser_dir" "$python_bin" -m playwright install chromium \
      || err 'Chromium install failed; system browser libraries may need manual installation'
  fi
  settings_tmp="$(mktemp "$NTN_HOME/.web-settings.XXXXXX")"
  if ! printf '%s\n' "$WEB_SETTINGS_JSON" | jq --arg browser "$WEB_CHOICE" --arg web_adapter "$WEB_ADAPTER" \
      --arg mcp "$MCP_CHOICE" --arg mcp_adapter "$MCP_ADAPTER" \
      --arg python "$python_bin" --arg profiles "$NTN_HOME/web/profiles" \
      --arg state "$NTN_HOME/web-state" --arg browsers "$browser_dir" '
      # Defaults fill missing fields only; skipped integrations and unknown
      # user-managed fields survive. A bundled browser owns its private runtime.
      {version:1,browser:{provider:"skip",executable:"",protocol:"ntn-web-provider/1"},
       mcp:{provider:"skip",executable:"",protocol:"mcp-stdio"},python:$python,
       profiles_dir:$profiles,state_dir:$state,browsers_path:$browsers} + . |
      if $browser != "skip" then
        .browser += {provider:$browser,executable:$web_adapter,protocol:"ntn-web-provider/1"}
      else . end |
      if $mcp != "skip" then
        .mcp += {provider:$mcp,executable:$mcp_adapter,protocol:"mcp-stdio"}
      else . end |
      if $browser == "bundled" then .python = $python | .browsers_path = $browsers
      elif .python == "" and $python != "" then .python = $python
      else . end
      ' > "$settings_tmp" 2>/dev/null; then
    rm -f "$settings_tmp"
    err 'could not create web settings'
  fi
  chmod 600 "$settings_tmp"
  mv -f "$settings_tmp" "$NTN_HOME/web-settings.json"
  ok 'optional web settings installed; no MCP client configuration changed'
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  exec bash "$(cd "$(dirname "$0")" && pwd)/install.sh" "$@"
fi
