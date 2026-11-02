# Hardening baseline: local network + perimeter

Two sides to audit, with different questions:

- **Local network (inside-out):** is the device itself hardened?
  Services, accounts, crypto, logging, updates.
- **Perimeter (outside-in):** what can be reached from outside? Open
  services, filters that don't restrict, NAT/port-forward, anti-spoofing.

Perimeter findings are usually the more fatal ones: plaintext service +
empty filter = the device can be reached by anyone on the WAN side.

## Cisco IOS — baseline

### Management plane
- [ ] `ip http server` off; if web is needed, `ip http secure-server` + AES ciphersuites only
- [ ] SSH v2 only: `ip ssh version 2`, `ip ssh time-out 60`, `ip ssh authentication-retries 3`
- [ ] VTY: `transport input ssh` (telnet off), `login local` or AAA, `access-class` restricting sources
- [ ] `enable secret` (not `enable password`), type 8/9 where supported
- [ ] `service password-encryption` enabled + no `password 0`/`secret 0`
- [ ] `exec-timeout` on line con/vty (not 0 0)
- [ ] Login banner present
- [ ] Users: least privilege, no user without a password

### Routing/perimeter
- [ ] uRPF on edge interfaces (`ip verify unicast source reachable-via rx`)
- [ ] Anti-spoofing ACL: block RFC1918 + multicast from WAN (BCP 38)
- [ ] Default route known and protected — don't change it without a gate
- [ ] `no ip source-route`, `no ip http active` (if unused)
- [ ] SNMP: v3 only, v1/v2c communities removed or ACL-restricted
- [ ] NTP configured (unsynchronized logs = broken forensics)
- [ ] `logging` to a syslog server, timestamp `datetime msec localtime`

### Official baseline sources
- CIS Cisco IOS 15 Benchmark (look up the latest version at audit time)
- Cisco Guide to Harden Cisco IOS Devices (cisco.com, the "Guide to Harden" document)

## MikroTik RouterOS — baseline

### Management plane
- [ ] `/ip service`: only `ssh`, `winbox`, `www-ssl`/`api-ssl` when needed;
      telnet/ftp/www/api off
- [ ] `/ip ssh set strong-crypto=yes`, host key type ecdsa/ed25519 where supported
- [ ] `/user`: no default `admin` user (rename), password policy + inactivity
      policy in place, least-privilege group
- [ ] `/tool mac-server` and `/tool bandwidth-server` restricted to LAN interfaces
- [ ] `/ip neighbor discovery-settings`: `discoverable` on LAN only, not WAN
- [ ] Latest RouterOS stable/long-term — not an EOL version

### Perimeter (input chain — what protects from the outside)
- [ ] `/ip firewall filter` chain=input: default drop, accept only:
      established/related, limited ICMP, management from specific IPs/VPN
- [ ] chain=forward: default drop for LAN→WAN traffic that isn't allowed,
      or at least fasttrack + drop invalid
- [ ] `/ip firewall service-port`: sip/h323/ftp helpers disabled when unused
- [ ] `/ip cloud` (DDNS Back to Home) off when unused
- [ ] `/ip firewall nat`: no dst-nat to management services from WAN
- [ ] Anti-spoof: `in-interface` filters for RFC1918 on the WAN interface (BCP 38)
- [ ] `/ip firewall raw` drop bogons from WAN

### Official baseline sources
- MikroTik help: "Securing your router" (help.mikrotik.com — look it up at audit time)
- MikroTik forum thread "How to secure your router" (community, context)

## Other brands (Huawei, Aruba, Arista, Juniper, Ruijie)

The `ntn` engine supports them, but no live audit battery has been written
yet. Approach:
1. Run the generic config audit (`cfg_audit.py`) — the general rules still apply
2. Grab `display current-configuration` / `show running-config` / `show config`
3. Check manually against the vendor baseline (see `threat-research.md` for URLs)
4. Add a parser in `sec_audit.py` once a device of that brand is available
   for testing — don't write rules from memory

## Severity scale used

- **CRIT** — reachable from outside without auth, or plaintext credentials,
  or a perimeter without filters. Must be fixed; blocks the verdict.
- **WARN** — weakens security but requires conditions (expired user, weak
  crypto with the service off, empty policy). Goes into the hardening plan.
- **INFO** — note/best practice, not urgent.
