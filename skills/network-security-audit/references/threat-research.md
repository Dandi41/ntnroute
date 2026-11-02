# Threat research procedure: CVEs, RFCs, OS versions, real-world incidents

Core rule: **the audit must be based on citable evidence.** A CVE finding
without an official link = rumor. Source order: vendor PSIRT/advisory →
NVD/CVE.org → community (for context, not evidence).

## 1. OS version first, always

Get the version from live output (`sec_audit.py` already prints `os=...`):

- Cisco: the `Cisco IOS Software ... Version 15.4(2)T4` line in `show version`
- MikroTik: `installed-version:` in `/system package update print`
- Huawei/Aruba/Arista/Juniper/Ruijie: `display version` / `show version` /
  `show version detail`

Also record the **channel** (RouterOS stable/long-term/testing) and the
**build date**. Testing = riskier; long-term = the security patch target.

## 2. Check the version's lifecycle status

Before CVEs: is this version still supported?

- Cisco: search for "End-of-Sale and End-of-Life Announcement <release>" on cisco.com
- MikroTik: the download page shows which releases are still receiving patches
- An EOL version is a CRIT finding in its own right: it will never receive patches

## 3. Search CVEs for that version

Query templates (web_search):

```
<vendor> <os> <version> CVE
<vendor> <os> <version> security advisory
site:<vendor-psirt-domain> <os> <version>
<os> <version> remote code exploitation
```

Official sources per vendor:

| Vendor | Advisory page | Notes |
|---|---|---|
| Cisco | https://sec.cloudapps.cisco.com/security/center/ + https://www.cisco.com/site/us/en/about/trust-center/security-advisories.html | use the Cisco Security Center to search per version |
| MikroTik | https://mikrotik.com/supportsec | advisories per CVE + release changelogs |
| Huawei | https://www.huawei.com/en/psirt | PSIRT bulletins |
| HPE Aruba | https://www.arubanetworks.com/support-services/security-bulletins/ | security bulletins per product |
| Arista | https://www.arista.com/en/support/advisories-notices | advisories & notices |
| Juniper | https://supportportal.juniper.net/ + https://www.juniper.net/documentation/ | JTSA/JSA bulletins |
| Ruijie | https://www.ruijie.com/en-global/support/ | support documents; limited PSIRT |

Cross-verify on NVD: https://nvd.nist.gov/vuln/search — a CVE that isn't on
NVD or the vendor PSIRT must not be reported as fact.

What to record per relevant CVE:

```
CVE-ID | affected versions (do they match the device version?) | CVSS severity
component/feature | does the device use that feature? | official link
```

**Relevance ≠ existence.** A CVE for a feature the device doesn't use is
still recorded, as INFO, not CRIT.

## 4. RFCs / best practices behind the audit rules

- **RFC 3871** — Best Current Practices for Securing IP Networks (basis of
  the checklist: no telnet, no SNMPv1/v2c, AAA, logging)
- **BCP 38 (RFC 2827/8704)** — anti-spoofing at the edge: ingress filters on
  outward-facing interfaces
- **RFC 1918** — private address ranges: the edge must not respond to or
  forward RFC1918 from the WAN
- **NIST SP 800-53** (AC-, IA-, SC- families) and **CIS Benchmarks**
  (CIS Cisco IOS 15 Benchmark, CIS MikroTik RouterOS Benchmark) — per-control
  baseline sources; look up the latest benchmark version at audit time
- **RFC 5246/8446** — TLS 1.2/1.3: RC4/3DES/DES ciphersuites must be off

For RFC text: https://www.rfc-editor.org/rfc/rfc<NUMBER>.txt

## 5. Real-world incidents

Sources used for context on "what actually happened":

- Official vendor forums (listed in the `network-troubleshooting` skill's
  `references/official-sources.md`)
- National CERTs: https://www.cert.id/ , https://www.certa.id/ , CERT Polska
  (cert.pl), CISA advisories (https://www.cisa.gov/news-events)
- Vendor blogs (the MikroTik blog has post-mortems of real cases)
- Reddit r/networking, r/mikrotik — operational context, not evidence

Query templates:

```
<vendor> <os> <feature> exploited in the wild
<vendor> router compromise 2025 OR 2026
<CVE-ID> exploitation observed
```

What to record from real-world incidents: the attack vector, the
configuration that caused it, and whether the audited device shares the
same pattern.

## 6. Report honesty

- Every CVE/version/EOL claim has a URL. Without a URL → write "not yet verified".
- Record the research date in the report — CVE lists go stale fast.
- Never call a device "secure". Say "no findings with this checklist, as of
  date X".
