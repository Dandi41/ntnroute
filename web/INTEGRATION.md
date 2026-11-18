# Independent Web GUI core — implemented subset

Python 3.10+, standard library; optional Playwright. Entry: `python3 -m web`
or parent integration `ntn web ...`. No Hermes dependency. No HTTP application
server is provided: this is an independent network-device Web GUI reader.

## Configuration and commands

Defaults use `$NTN_HOME` (fallback `~/.ntnroute`): `devices.json`,
`web/profiles`, `web-state`, `web-settings.json`. Installer settings version 1:
`browser.provider` = bundled/existing/skip, `browser.executable`, `profiles_dir`,
`state_dir`, `browsers_path` are consumed. `PLAYWRIGHT_BROWSERS_PATH` is set from
`browsers_path`. Installer `python` selects a launcher interpreter, not something
this running Python process executes. `mcp.provider/executable` are integration
selection metadata; direct `mcp` explicitly starts the bundled server, never
silently launches another MCP executable or edits client settings.

Global overrides (before command): `--settings`, `--inventory`, `--profiles`,
`--state-dir`, `--provider bundled|playwright|external|skip`,
`--provider-command /absolute/executable`, `--allow-http-credentials`.
Provider defaults to skip without configuration. Metadata works when skipped.
TLS verification is strict by default; an explicit per-device `web.tls_verify: false`
is supported for authorized lab/self-signed targets, not as a global default.

Commands (JSON stdout; operational errors JSON stderr, exit 1):

- `profiles`, `capabilities`
- `validate-profile PROFILE_ID` (root-contained id, **not an arbitrary file path**)
- `inspect --device REF --profile ID`
- `learn --device REF --profile ID`: bounded observation from a reviewed profile,
  with optional authentication and non-value DOM control metadata. No automatic
  crawling, probing, training or candidate promotion.
- `plan --device REF --profile ID --action vlan.configure --params '{"vlan":20}' --recovery 'Use local console and saved configuration'`
- `review --plan SHA256`
- `approve --plan SHA256`: displays exact plan and requires typed confirmation on
  `/dev/tty`. No stdin/boolean/hash-as-consent shortcut. Unix operator channel.
- `apply --plan SHA256`, `rollback --plan SHA256`: **always refuse, no submission**.
- `mcp`: minimal newline-delimited JSON-RPC MCP stdio, protocol 2024-11-05,
  initialize/ping/tools/list/tools/call. Tools expose profiles, capabilities,
  inspect, plan, review, apply, rollback; **no approval issuance**. Notifications
  never execute tools. No resources, prompts, cancellation or HTTP transport.

## Inventory and trust

Uses canonical `{next_id, devices:[], checkpoints:[], audit:[]}` inventory,
selected by unique id, hostname or IP. Selected record must explicitly contain
`web: {origin: "https://device.example", profile: "reviewed-profile-id"}`.
Web username/password override top-level username/user and password/pass.
SSH IP never implicitly authorizes a browser origin. Inventory is read-only:
no inventory locks or writes, no changes to SSH profiles/brands or live devices.

Settings, inventory, profile root, private state and operator OS account are
trusted. Do not grant an untrusted agent shell/filesystem write access to these
and then treat the same account as an approval boundary. The MCP protocol
cannot issue approvals. Review plan bodies are content-addressed, exclusive
create, mode 0600 under mode 0700 state, include baseline/profile digest,
parameters, recovery and expiry. Edits invalidate the ID. This is immutable-by-
interface, **not** tamperproof against the trusted filesystem owner.

Provider responses have exact field/origin checks and identity equality; literal
credential echoes are rejected. Profiles forbid secret-like field names. Field
mapping must still be reviewed: arbitrary configuration text may contain secrets
that cannot reliably be recognized. Never put secrets in params/recovery.
Snapshots are partial operational state, not backups.

## Honest support limits

- WebFig and CData candidate skeletons cannot connect. Authentication-only
  profiles also exist with explicit login/success selectors. These do not prove
  live firmware compatibility or authorize configuration operations. Review all
  paths, selectors and exact identity markers on an authorized lab first.
- Even GET links may mutate devices: reviewed navigation paths are required.
- Bundled Playwright implements ephemeral authenticated login with JavaScript,
  same-origin routing, bounded requests and exact success markers. Workers and
  WebSockets are blocked; no session storage export, traces or screenshots.
  Authentication and assets require exact reviewed path/method/count declarations,
  including query strings. Shipped auth profiles have empty endpoint lists and
  intentionally fail closed until firmware review supplies these declarations.
  Reviewed selectors alone do not establish operational login support.
- External provider is explicit trusted integration; see PROVIDER.md. Core
  enforces response shape/origin but cannot sandbox or prove provider isolation.
- ONU/WAN/VLAN parameter declarations and review-only plans exist, not write
  support. No vendor writes, automatic rollback, drift/recovery execution,
  persisted mutation intent, per-device mutation serialization, or post-write
  verification has been implemented. These are prerequisites **before** enabling
  any mutation. Current fail-closed apply performs zero provider calls, even if
  approved or repeatedly invoked. A supported management-path change would also
  require structured new access path and offline recovery validation.
- Stdlib subprocess capture is timeout bounded but not streaming-memory bounded;
  external executables must be trusted and output bounded. Local private state
  assumes an operator-controlled filesystem, not adversarial same-UID races.

## Local tests

From repository root: `python3 -m unittest discover -s tests/web -v`.
Temporary canonical inventories and a fake executable only; no live inventory
or devices. Optional Playwright/browser end-to-end tests and lab firmware
validation remain pending. No Playwright package/browser download is required
for these tests.
