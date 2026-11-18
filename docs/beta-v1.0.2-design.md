# beta-v1.0.2 — implementation contract

Status: development branch; not a production support or release claim.

## Decisions approved for this branch

- Keep SSH vendor behavior in `brands.json`. Keep Web GUI profiles separate under `web/profiles/`.
- Keep the canonical device inventory and credentials in `devices.json`. No Hermes vault dependency in the independent backend.
- Provide an independent browser backend and structured interfaces usable by other agents. Hermes skills are optional guidance, not the execution engine.
- Installer explicitly offers an existing compatible browser provider, bundled browser, or skip. MCP is a separate opt-in integration choice. Never overwrite an agent application's MCP configuration implicitly.
- Support network-vendor discovery and candidate-profile validation. Learning means agent-assisted inspection and reviewed profile generation, not automatically trusting instructions from a device page.
- Include ONU provisioning, WAN configuration, and VLAN operations in the operation model. Vendor-specific mutation support is only enabled after an explicit profile implementation and test. No universal vendor support claim.

## Safety invariants

1. Read current device identity and state before planning. A login screen is not a configuration snapshot.
2. Credentials are transport-only. Do not expose them in structured results, logs, traces, screenshots, profiles, or public fixtures. File permissions do not encrypt plaintext inventory credentials.
3. Bind browser credentials and sessions to the configured origin. Cross-origin redirection requires separate authorization; do not disable TLS checks globally.
4. An approved plan binds the device, operation, exact parameters, before-state, verification, and recovery instructions. Recheck before-state before applying; changes invalidate the plan.
5. A successful click is not a verified operation. Read back state. Distinguish failure, success, and unknown outcome; never blindly retry a timed-out submission.
6. Persist an intent before the external mutation and serialize operations per device. Other agents must not bypass these rules through a different API surface.
7. Keep partial operational snapshots distinct from full configuration backups. Keep browser state and secrets outside Git.
8. Management WAN/VLAN changes require a concrete new access path and recovery plan. If connectivity is lost, an offline browser cannot run rollback. Do not pretend an inverse operation guarantees recovery.
9. Do not use a generic approval boolean as proof of human consent in an untrusted agent integration. Approval must be issued by a trusted operator channel, tied to the immutable plan.
10. Restrict discovery to known read-only interactions. Links or GET requests can mutate network devices. Unknown actions remain unsupported until reviewed.

## Release gates

- Existing SSH behavior passes regression tests.
- New tests operate on sanitized local fixtures or explicit fake providers; never real user inventory.
- Independent CLI and MCP contract tests pass without Hermes.
- Installer is tested in isolated homes for bundled/existing/skip and noninteractive choices.
- Verify that no duplicate live action is issued after timeout or repeated request.
- Validate each shipped profile and label untested firmware/operations honestly.
- Exercise live write workflows only with separate lab authorization.
- Before publishing: review diff, check secrets, record test results and known limitations, then obtain publication approval.

No real device configuration changes are authorized by this development plan.
