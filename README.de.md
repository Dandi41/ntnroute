# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

SSH-basierte Network-Device-Engine für KI-Agenten: ein kompaktes Geräte-Inventar, sichere CLI-Ausführung, Config-Backup und **freigabepflichtige** Konfigurationsänderungen mit automatischem Rollback — plus eine Sammlung von [Hermes-Agent](https://hermes-agent.nousresearch.com)-Skills, die dem Agenten die verantwortungsvolle Bedienung beibringen.

## Was es tut

- **Inventar** — Geräte einmal registrieren (`ntn add`); die Engine testet die SSH-Verbindung, zieht Hostname und laufende Konfiguration und speichert erst dann. Gespeichert wird in einer einfachen JSON-Datei (`~/.ntnroute/devices.json`, Modus 600), die Agent-Neustarts überlebt.
- **Nur-Lese-Zugriff** — `ntn exec` führt `show ...`-Befehle aus und liefert das Transkript zurück.
- **Config-Backup** — `ntn sync` zieht die Running-Config ins Inventar und in eine Backup-Datei mit Zeitstempel.
- **Freigabepflichtige Config-Änderungen** — `ntn config` führt aus: Snapshot vor der Änderung → anwenden → speichern → Post-Check (jede Skriptzeile muss in der neuen Konfiguration erscheinen) → Inventar-Update. Gerät vor der Änderung nicht erreichbar? Abbruch. Gerät verwirft eine Zeile? Fehler wird gemeldet, das Inventar bleibt unangetastet.
- **Rollback** — jede Änderung legt einen Checkpoint an; `ntn rollback` wendet das gespeicherte Rückgängig-Skript an.
- **Audit-Trail** — `ntn audit` zeigt die letzten Operationen.

Kein Python, kein Agent, kein Daemon: nur **bash + jq + OpenSSH**.

## Unterstützte Plattformen

| Hersteller | Modus | Config abrufen | Speichern |
|---|---|---|---|
| Cisco IOS | interaktives PTY | `show running-config` | `write memory` |
| Huawei | interaktives PTY | `display current-configuration` | `commit` |
| Aruba / Arista / Ruijie / Juniper | interaktives PTY | herstellerspezifisch | herstellerspezifisch |
| MikroTik RouterOS | Exec-Modus (`ssh -T`) | `/export` | automatisch |

Legacy-Krypto (alte Cisco-Images) wird behandelt: `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1` werden bei Bedarf ausgehandelt.

## Installation

Voraussetzungen: Linux/macOS mit `bash`, `jq`, `ssh` (OpenSSH).

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

## Schnellstart

```bash
# Gerät registrieren (Verbindung wird zuerst getestet; bei Fehler wird nichts gespeichert)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

ntn list                # nummeriertes Inventar
ntn show 1              # Details + gespeicherte Config
ntn ping 1              # ICMP-Check
ntn exec 1 'show ip interface brief' 'show ip route'
ntn sync all            # Running-Config aller Geräte abziehen
ntn audit 10            # die letzten 10 Operationen
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

- Passwörter werden **im Klartext** in `~/.ntnroute/devices.json` gespeichert (Modus 600, nur Eigentümer). Das ist ein bewusster Kompromiss für ein Lab-Tool — nicht auf Produktivsysteme richten, wenn das unakzeptabel ist.
- `ntn show <ref>` maskiert Passwörter standardmäßig; `--reveal` zeigt sie.
- `devices.json` und `backups/` sind in .gitignore. **Niemals committen.**

## Status & Ehrlichkeit

End-to-end an realen Geräten erprobt: Cisco IOS 15.4 und MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, Config + Post-Check, Rollback, destruktive Befehle, Wächter für nicht erreichbare Geräte, Wächter für Gerätefehler).

Die Codepfade für Huawei, Aruba, Arista, Ruijie und Juniper existieren, wurden aber **noch** nicht an realer Hardware getestet — als experimentell behandeln und Probleme über Issues melden.

## Lizenz

[MIT](LICENSE) © Dandi Suryadi
