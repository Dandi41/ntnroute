# beta-v1.0.2 implementation status

Development snapshot; not a release readiness claim.

## Implemented

- Independent `ntn web` Python JSON CLI and minimal stdio MCP interface.
- Separate browser and MCP installer choices; noninteractive safe skip.
- Separate Web GUI profiles and internal inventory credential loading.
- Ephemeral Playwright login implementation with exact success markers, origin guards, bounded inspection and optional non-value DOM control metadata.
- Authentication-only WebFig/CData profiles. These are not firmware-certified adapters; fixture tests alone cannot establish compatibility with actual devices.
- Plan/approval foundation; unsupported writes fail closed, even after approval.

## Verification

Commands run from repository root:

```
python3 -m unittest discover -s tests -p 'test_web*.py'
python3 -m unittest discover -s tests/web -v
bash -n ntn install.sh install-web.sh
git diff --check
```

Latest system-Python run: 19 installer/dispatch tests and 46 core/provider tests passed, including JSON Schema validation. The real-browser fixture class was skipped because Playwright is not installed in system Python. Syntax and whitespace checks passed. These are mocked/unit results, not firmware certification. An independent review found no outstanding defect in the four targeted security/settings fixes.

System Python lacks ensurepip. An isolated pip-free venv was created under the scratch directory and populated using system pip's --python option; Playwright and Chromium installed successfully without changing system packages. The isolated run executed 53 core/provider/browser tests: 52 passed and only optional JSON Schema validation was skipped (it passed in the system-Python run). All seven real Chromium loopback fixture tests passed, covering login markers, bounded metadata, credential echo rejection, off-origin containment and undeclared same-origin requests. These fixtures simulate device interfaces; they do not certify real WebFig/CData firmware.

## Not supported / release blockers

- ONU provisioning and WAN/management VLAN writes, including firmware-specific verification and recovery.
- Live-device compatibility proof for authentication profiles.
- Generic autonomous vendor learning: bounded control metadata is not a trained or validated adapter.
- End-to-end bundled browser installation/login validation in this environment.
- Full configuration backup and guaranteed rollback after management connectivity loss.

Authentication and asset requests require exact reviewed path, method and bounded request counts, including exact query strings. Shipped WebFig/CData authentication templates deliberately have empty endpoint declarations: login fails closed until authorized firmware endpoint review fills these in. Do not interpret their reviewed UI selectors as operational login support.

No production device configuration was changed during development. No commit or push is part of this verification.
