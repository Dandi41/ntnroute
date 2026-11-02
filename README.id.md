# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

Engine perangkat jaringan berbasis SSH untuk AI agent: inventaris device, eksekusi CLI yang aman, backup config, dan perubahan konfigurasi **dengan gerbang persetujuan** plus rollback otomatis — lengkap dengan kumpulan skill [Hermes Agent](https://hermes-agent.nousresearch.com) yang mengajarkan agent cara memakainya secara bertanggung jawab.

## Apa yang dilakukan

- **Inventaris** — daftarkan device sekali (`ntn add`); engine menguji koneksi SSH, menarik hostname dan running config, baru menyimpan. Disimpan di file JSON biasa (`~/.ntnroute/devices.json`, mode 600) yang bertahan antar restart agent.
- **Akses read-only** — `ntn exec` menjalankan perintah `show ...` dan mengembalikan transkripnya.
- **Backup config** — `ntn sync` menarik running config ke inventaris + file backup bertimestamp.
- **Perubahan config bergerbang** — `ntn config` menjalankan: snapshot pra-perubahan → apply → save → post-check (setiap baris script harus muncul di config baru) → update inventaris. Device tak terjangkau sebelum perubahan? Abort. Device menolak satu baris? Dilaporkan gagal, inventaris tidak disentuh.
- **Rollback** — setiap perubahan menyimpan checkpoint; `ntn rollback` menerapkan script pembatalnya.
- **Jejak audit** — `ntn audit` menampilkan operasi terakhir.

Engine hanya bash + jq + OpenSSH — tanpa Python, tanpa agent, tanpa daemon.
Skrip pembantu (`triage`, `rollback_gen`, `ios_session.sh`) juga bash + awk;
hanya gerbang audit opsional (`cfg_audit.py`, `sec_audit.py`) yang memakai
Python stdlib.

## Platform yang didukung

| Vendor | Mode | Ambil config | Simpan |
|---|---|---|---|
| Cisco IOS | PTY interaktif | `show running-config` | `write memory` |
| Huawei VRP | PTY interaktif | `display current-configuration` | `save` + konfirmasi |
| Aruba / Arista / Ruijie | PTY interaktif | `show running-config` | `write memory` |
| Juniper Junos | PTY interaktif | `show configuration \| display set` | `commit` (di dalam config mode) |
| Fortinet FortiGate | PTY interaktif | `show full-configuration` | otomatis (langsung aktif) |
| MikroTik RouterOS | exec-mode (`ssh -T`) | `/export` | otomatis |

Kripto lawas (image Cisco tua) ditangani: `diffie-hellman-group14-sha1`, `ssh-rsa`, `aes128-cbc`, `hmac-sha1` dinegosiasikan saat perlu.

## Beradaptasi dengan vendor baru

Perilaku per-brand ada di `~/.ntnroute/brands.json` — edit file itu untuk mendukung vendor yang belum dikenal engine, atau menimpa bawaan (termasuk saat firmware berubah). Satu entri cukup:

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

Field: `paging`, `secret_cmd`, `config_enter`, `config_leave`, `save_lines` (array), `save_delay`, `config_show`, `hostname_show`, `hostname_field` (`hostname`|`sysname`|`host-name`|`colon`), `err_pattern` (grep -E), `negate_prefix` (dipakai `rollback_gen`). Brand tak dikenal tanpa profil memakai default generik ala Cisco dan melewatkan langkah save. Installer tidak pernah menimpa `brands.json` milikmu.

## Instalasi

Prasyarat: Linux/macOS dengan `bash`, `jq`, `ssh` (OpenSSH).

```bash
git clone https://github.com/Dandi41/ntnroute.git
cd ntnroute
./install.sh
```

Installer akan:

1. memeriksa `jq` dan `ssh`,
2. memasang engine ke `~/.ntnroute/ntn` (mode 700) dan symlink sebagai `~/.local/bin/ntn`,
3. membuat `~/.ntnroute/` dengan inventaris kosong (mode 600),
4. kalau kamu memakai [Hermes Agent](https://hermes-agent.nousresearch.com), menyalin lima skill ke `~/.hermes/skills/networking/`.

## Mulai cepat

```bash
# daftarkan device (koneksi dites dulu; gagal = tidak disimpan)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

ntn list                # inventaris bernomor
ntn show 1              # detail + config tersimpan
ntn ping 1              # cek ICMP
ntn exec 1 'show ip interface brief' 'show ip route'
ntn sync all            # tarik running-config semua device
ntn audit 10            # 10 operasi terakhir
```

Perubahan config selalu: rencana → persetujuan → apply → verifikasi. Skill `network-change-management` memaksa gerbang persetujuan dan membuat script rollback sebelum apa pun menyentuh device.

## Skill yang disertakan

| Skill | Fungsi |
|---|---|
| `ntnroute` | Aturan alur kerja inti engine `ntn` (inventaris, exec, config, rollback) |
| `network-device-cli` | Mekanika sesi SSH per vendor, kripto lawas, parsing kredensial |
| `network-change-management` | Gerbang rencana/persetujuan, audit blast-radius, pembuatan rollback |
| `network-troubleshooting` | Diagnosa OSI-first dengan referensi perintah vendor |
| `network-security-audit` | Audit hardening lokal + perimeter dari config device |

## Catatan keamanan

- Password disimpan **dalam plaintext** di `~/.ntnroute/devices.json` (mode 600, hanya owner). Ini trade-off sadar untuk tool lab — jangan arahkan ke produksi kalau tidak bisa diterima.
- `ntn show <ref>` menyamarkan password secara default; `--reveal` menampilkannya.
- `devices.json` dan `backups/` di-gitignore. **Jangan pernah di-commit.**

## Status & kejujuran

Terbukti end-to-end di perangkat nyata: Cisco IOS 15.4 dan MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, config + post-check, rollback, perintah destruktif, guard device tak terjangkau, guard error device). Brand lainnya (Huawei VRP, Arista EOS, Aruba AOS-CX, Ruijie RGOS, Juniper Junos, Fortinet FortiGate) diverifikasi dengan cara yang sama terhadap CLI vendor yang diemulasi (harness uji lokal, bukan bagian dari toolkit).

Jalur kode untuk Huawei, Aruba, Arista, Ruijie, dan Juniper ada tapi **belum** pernah diuji ke perangkat nyata — anggap eksperimental dan laporkan lewat Issues.

## Dukung

Kalau ntnroute membantu pekerjaanmu, kreator boleh dibelikan lemper 🙂: **[tako.id/Lemper41](https://tako.id/Lemper41)**

Temukan saya di [Instagram](https://www.instagram.com/sdandi_41/) dan [LinkedIn](https://www.linkedin.com/in/dandi-suryadi-a29276253/).

## Lisensi

[MIT](LICENSE) © Dandi Suryadi
