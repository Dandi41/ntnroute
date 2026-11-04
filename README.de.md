# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

SSH-basierte Network-Device-Engine für KI-Agenten: ein kompaktes Geräte-Inventar, sichere CLI-Ausführung, Config-Backup und **freigabepflichtige** Konfigurationsänderungen mit automatischem Rollback — plus eine Sammlung von [Hermes-Agent](https://hermes-agent.nousresearch.com)-Skills, die dem Agenten die verantwortungsvolle Bedienung beibringen.

## Was es tut

- **Inventar** — Geräte einmal registrieren (`ntn add`); die Engine testet die SSH-Verbindung, zieht Hostname und laufende Konfiguration und speichert erst dann. Gespeichert wird in einer einfachen JSON-Datei (`~/.ntnroute/devices.json`, Modus 600), die Agent-Neustarts überlebt.
- **Nur-Lese-Zugriff** — die Engine führt `show ...`-Befehle auf Anforderung aus und liefert das Transkript zurück.
- **Config-Backup** — `ntn sync` zieht die Running-Config ins Inventar und in eine Backup-Datei mit Zeitstempel; jede erfolgreiche Änderung (und jeder Rollback) veröffentlicht ein Archivpaar unter `~/.ntnroute/backups/<host>/<YYYY-MM>/`, maximal 4 pro Monat, aufbewahrt für die letzten 3 Monate plus einen jährlichen Keeper.
- **Freigabepflichtige Config-Änderungen** — `ntn config` führt aus: Snapshot vor der Änderung → anwenden → speichern → Inventar-/Archivaktualisierung. Fehler gibt es nur bei einem Gerätefehler, einer verlorenen Sitzung oder einem fehlenden Vorab-Snapshot. Der funktionale Erfolg wird danach mit geplanten Nur-Lese-Prüfungen am Gerät bestätigt.
- **Rollback** — jede Änderung legt einen Checkpoint an; das gespeicherte Rückgängig-Skript kann auf Anforderung wiedereingespielt werden.
- **Audit-Trail** — jeder Config-/Rollback-Vorgang wird *vor* dem Zugriff auf das Gerät protokolliert (`config-pending`) und dann abgeschlossen: `config-ok`/`config-failed`/`config-aborted` plus ein `config-started`-Marker für die Akte. Die Filter des Änderungsprotokolls dienen Troubleshooting und Security-Review: `pending` (Vorgänge ganz ohne Ergebnis — Prozess mitten im Apply beendet), `failed`, `config`, `all`. Einträge älter als 105 Tage werden automatisch entfernt; Security-Audit-Läufe werden separat aufgezeichnet, nur wenn tatsächlich ein Audit durchgeführt wird.

Die Engine besteht nur aus bash + jq + OpenSSH — kein Python, kein Agent, kein
Daemon. Die Hilfsskripte (`triage`, `rollback_gen`, `ios_session.sh`) sind
ebenfalls bash + awk; nur die optionalen Audit-Gates (`cfg_audit.py`,
`sec_audit.py`) nutzen Standard-Python.

## Unterstützte Plattformen

| Hersteller | Modus | Config abrufen | Speichern |
|---|---|---|---|
| Cisco IOS | interaktives PTY | `show running-config` | `write memory` |
| Huawei VRP | interaktives PTY | `display current-configuration` | `save` + Bestätigung |
| Aruba / Arista / Ruijie | interaktives PTY | `show running-config` | `write memory` |
| Juniper Junos | interaktives PTY | `show configuration \| display set` | `commit` (im Konfigurationsmodus) |
| Fortinet FortiGate | interaktives PTY | `show full-configuration` | automatisch (wirkt sofort) |
| MikroTik RouterOS | Exec-Modus (`ssh -T`) | `/export verbose` | automatisch |
| Linux (SSH) | Exec-Modus (`ssh -T`) | `uname -a` + os-release-Snapshot | — (kein Config-Modell) |
| Windows (OpenSSH, cmd.exe) | exec-arg (`ssh host "cmd"`) | `systeminfo`-Snapshot | — (kein Config-Modell) |

Legacy-Krypto (alte Cisco-Images) wird behandelt: `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1` werden bei Bedarf ausgehandelt.

## Anpassung an neue Hersteller

Das Verhalten pro Marke liegt in `~/.ntnroute/brands.json` — dort editieren, um einen unbekannten Hersteller zu unterstützen oder einen eingebauten zu überschreiben (Firmware-Änderungen eingeschlossen). Ein Eintrag genügt:

```json
{
  "zte": {
    "paging": "terminal length 0",
    "config_enter": "configure terminal",
    "config_leave": "end",
    "save_lines": ["write memory"],
    "config_show": "show running-config",
    "hostname_show": "show running-config | include hostname",
    "hostname_field": "hostname",
    "err_pattern": "(^%|Invalid input)"
  }
}
```

Felder: `paging`, `secret_cmd`, `config_enter`, `config_leave`, `save_lines` (Array), `save_delay`, `config_show`, `hostname_show`, `hostname_field` (`hostname`|`sysname`|`host-name`|`colon`), `err_pattern` (grep -E), `negate_prefix` (von `rollback_gen` genutzt). Unbekannte Marken ohne Profil erhalten generische Cisco-ähnliche Defaults und überspringen den Save-Schritt. Der Installer überschreibt deine `brands.json` nie.

## Format der Geräte-Datenbank

Das Inventar liegt in `~/.ntnroute/devices.json` (Modus 600, gitignored — niemals die echte Datei committen). Die Engine liest und schreibt ein exaktes Format: `next_id`, `devices[]`, `checkpoints[]`, `audit[]`, `security_audits[]`. Siehe [`examples/devices.example.json`](examples/devices.example.json) als ausgefüllte Referenz mit Platzhalter-Zugangsdaten — verweise KI-Agents oder Skripte auf diese Datei, damit sie dieselben Feldnamen verwenden statt eigene zu erfinden.

## Installation

Voraussetzungen: Linux, macOS oder Windows (über Git for Windows) mit `bash`, `jq`, `ssh` (OpenSSH). macOS benötigt GNU coreutils für `timeout` (`brew install coreutils`).

```bash
git clone https://github.com/Dandi41/ntnroute.git
cd ntnroute
./install.sh
```

Der Installer:

1. prüft `jq` und `ssh`,
2. installiert die Engine nach `~/.ntnroute/ntn` (Modus 700) und verlinkt sie als `~/.local/bin/ntn`,
3. erstellt `~/.ntnroute/` mit leerem Inventar (Modus 600),
4. kopiert bei [Hermes Agent](https://hermes-agent.nousresearch.com) die fünf Skills nach `~/.hermes/skills/networking/`.

### Windows (nativ, ohne WSL)

NTnRoute läuft auch nativ unter Windows über Git for Windows (MSYS2-bash) — kein WSL nötig.

1. Installiere [Git for Windows](https://git-scm.com/download/win) — es bringt `bash` und OpenSSH-`ssh` mit.
2. Öffne **Git Bash** und führe aus:

```bash
git clone -b beta https://github.com/Dandi41/ntnroute.git ~/ntnroute
cd ~/ntnroute
bash install.sh
```

Unter Windows erkennt der Installer MSYS2 automatisch: die Engine landet in `~/.ntnroute/ntn`, `ntn` wird als Kopie in `~/.local/bin` abgelegt (Windows-Symlinks brauchen Rechte), und fehlt `jq`, lädt der Installer `jq.exe` nach `~/.ntnroute/bin` (die Engine ergänzt dieses Verzeichnis selbst zur `PATH`). Findet die Shell `ntn` nach der Installation nicht, ergänze `~/.local/bin` im PATH, wie der Installer vorschlägt. Alle Befehle verhalten sich genau wie unter Linux/macOS; interaktive Vendor-Sitzungen laufen über die MSYS2-PTY. Die Windows-Unterstützung liegt im Zweig `beta`, bis er gemergt ist.

## Schnellstart

Wenn du unsicher bist, wie du die NTnRoute-Engine verwendest, schreibe deinem Agenten `ntn` oder `ntn help`. Der Agent zeigt das verfügbare öffentliche Menü und führt durch den passenden Ablauf.

```bash
# Gerät registrieren (Verbindung wird zuerst getestet; bei Fehler wird nichts gespeichert)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

# öffentliches Inventar- und Konfigurationsübersichtsmenü
ntn list
ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]
ntn remove <number|id>
ntn show <ref>
ntn sync <ref|all>
```

Eine Config-Änderung läuft immer: Plan → Freigabe → Anwenden → Verifizieren. Das mitgelieferte Skill `network-change-management` erzwingt die Freigabe-Schranke und erzeugt das Rollback-Skript, bevor irgendetwas das Gerät berührt.

## Die Skills

| Skill | Zweck |
|---|---|
| `ntnroute` | Kern-Workflow-Regeln der `ntn`-Engine (Inventar, exec, config, Rollback) |
| `network-device-cli` | SSH-Sitzungsmechanik je Hersteller, Legacy-Krypto, Credential-Parsing |
| `network-change-management` | Plan-/Freigabe-Schranke, Blast-Radius-Audit, Rollback-Erzeugung |
| `network-troubleshooting` | OSI-first-Diagnose mit Hersteller-Kommandoreferenzen |
| `network-security-audit` | Audit von lokaler Härtung + Perimeter der Gerätekonfigurationen |

## Sicherheitshinweise

- Passwörter werden **im Klartext** in `~/.ntnroute/devices.json` gespeichert (Modus 600, nur für den Besitzer). Bewahre diese Datei gut auf, damit sie nicht über die Maschine hinaus verbreitet wird.
- `ntn show <ref>` maskiert Passwörter standardmäßig.
- Config-Backups unter `~/.ntnroute/backups/` enthalten dieselben Geräte-Geheimnisse — mit derselben Sorgfalt behandeln.
## Status & Ehrlichkeit

End-to-end an realen Geräten erprobt: Cisco IOS 15.4 und MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, Config + Post-Check, Rollback, destruktive Befehle, Wächter für nicht erreichbare Geräte, Wächter für Gerätefehler). Die übrigen Marken (Huawei VRP, Arista EOS, Aruba AOS-CX, Ruijie RGOS, Juniper Junos, Fortinet FortiGate) wurden auf die gleiche Weise gegen emulierte Hersteller-CLIs geprüft (lokales Test-Harness, nicht Teil des Toolkits).

Die Codepfade für Huawei, Aruba, Arista, Ruijie und Juniper existieren, wurden aber **noch** nicht an realer Hardware getestet — als experimentell behandeln und Probleme über Issues melden.

## Unterstützen

Wenn ntnroute dir Zeit spart, kannst du dem Ersteller einen Lemper ausgeben 🙂 — einen indonesischen Klebreis-Snack: **[tako.id/Lemper41](https://tako.id/Lemper41)**

Du findest mich auf [Instagram](https://www.instagram.com/sdandi_41/) und [LinkedIn](https://www.linkedin.com/in/dandi-suryadi-a29276253/).

## Lizenz

[MIT](LICENSE) © Dandi Suryadi
