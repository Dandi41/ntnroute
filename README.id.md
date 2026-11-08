# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

Engine perangkat jaringan berbasis SSH untuk AI agent: inventaris device, eksekusi CLI yang aman, backup config, dan perubahan konfigurasi **dengan gerbang persetujuan** plus rollback otomatis — lengkap dengan kumpulan skill [Hermes Agent](https://hermes-agent.nousresearch.com) yang mengajarkan agent cara memakainya secara bertanggung jawab.

## Apa yang dilakukan

- **Inventaris** — daftarkan device sekali (`ntn add`); engine menguji koneksi SSH, menarik hostname dan running config, baru menyimpan. Disimpan di file JSON biasa (`~/.ntnroute/devices.json`, mode 600) yang bertahan antar restart agent.
- **Akses read-only** — engine menjalankan perintah `show ...` sesuai permintaan dan mengembalikan transkripnya.
- **Cadangan config** — `ntn sync` menyimpan konfigurasi berjalan ke inventaris dan menyimpan snapshot bertanda waktu; setiap perubahan (dan rollback) yang sukses menerbitkan pasangan arsip di `~/.ntnroute/backups/<host>/<YYYY-MM>/`. Setiap folder bulan menampung maksimal 4 pasangan perubahan dan 4 snapshot sync/add, disimpan 3 bulan terakhir plus 1 arsip tahunan; file lepas dari versi lama dipindahkan ke tata letak ini secara otomatis.
- **Perubahan config bergerbang** — `ntn config` menjalankan: snapshot pra-perubahan → apply → save → refresh inventaris/arsip. Gagal hanya jika device menolak perintah, sesi terputus, atau snapshot pra-perubahan tidak tersedia. Keberhasilan fungsional dibuktikan setelahnya lewat pemeriksaan device read-only yang direncanakan.
- **Rollback** — setiap perubahan menyimpan checkpoint; script pembatalnya bisa diputar ulang saat diminta.
- **Jejak audit** — setiap percobaan config/rollback dicatat *sebelum* menyentuh device (`config-pending`), lalu disettle: `config-ok`/`config-failed`/`config-aborted` + penanda `config-started` untuk riwayat. Filter jejak perubahan untuk troubleshooting dan audit keamanan: `pending` (percobaan tanpa verdict sama sekali — proses mati di tengah apply), `failed`, `config`, `all`. Entri yang berumur lebih dari 105 hari dipangkas otomatis.

Engine hanya bash + jq + OpenSSH — tanpa Python, tanpa agent, tanpa daemon.
Skrip pembantu (`rollback_gen`, `ios_session.sh`) juga bash + awk. Audit dan
troubleshooting adalah prosedur terpandu agent: tidak ada skrip audit/triage bawaan.

## Platform yang didukung

| Vendor | Mode | Ambil config | Simpan |
|---|---|---|---|
| Cisco IOS | PTY interaktif | `show running-config` | `write memory` |
| Huawei VRP | PTY interaktif | `display current-configuration` | `save` + konfirmasi |
| Aruba / Arista / Ruijie | PTY interaktif | `show running-config` | `write memory` |
| Juniper Junos | PTY interaktif | `show configuration \| display set` | `commit` (di dalam config mode) |
| Fortinet FortiGate | PTY interaktif | `show full-configuration` | otomatis (langsung aktif) |
| MikroTik RouterOS | exec-mode (`ssh -T`) | `/export verbose` | otomatis |
| Linux (SSH) | exec-mode (`ssh -T`) | snapshot `uname -a` + os-release | — (tanpa model config) |
| Windows (OpenSSH, cmd.exe) | exec-arg (`ssh host "cmd"`) | snapshot `systeminfo` | — (tanpa model config) |

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

## Format database device

Inventaris tersimpan di `~/.ntnroute/devices.json` (mode 600, gitignore — jangan pernah commit file aslinya). Engine membaca dan menulis bentuk yang pasti: `next_id`, `devices[]`, `checkpoints[]`, `audit[]`. Lihat [`examples/devices.example.json`](examples/devices.example.json) sebagai referensi yang sudah terisi dengan kredensial contoh — arahkan AI agent atau script ke file itu agar menulis nama field yang sama, bukan mengarang sendiri.

## Instalasi

Prasyarat: Linux, macOS, atau Windows (lewat Git for Windows) dengan `bash`, `jq`, `ssh` (OpenSSH). macOS butuh GNU coreutils untuk `timeout` (`brew install coreutils`).

```bash
git clone https://github.com/Dandi41/ntnroute.git
cd ntnroute
./install.sh
```

Installer akan:

1. memeriksa `jq` dan `ssh`,
2. memasang engine ke `~/.ntnroute/ntn` (mode 700) dan symlink sebagai `~/.local/bin/ntn`,
3. membuat `~/.ntnroute/` dengan inventaris kosong (mode 600),
4. kalau kamu memakai [Hermes Agent](https://hermes-agent.nousresearch.com), menyelaraskan lima skill ke `~/.hermes/skills/networking/` lewat manifest (`.ntn_manifest`): file milik repo diperbarui, file yang dihapus dari repo dibersihkan, dan apa pun yang bukan hasil instalasi installer — referensi buatan agent, editan lokal — dipertahankan (file repo yang diedit lokal disimpan di sebelahnya sebagai `<file>.local-<ts>`). Snapshot pohon skill sebelum install mendarat di `~/.ntnroute/backups/` (5 terakhir disimpan). Flag: `--dry-run` menampilkan rencana tanpa menyentuh apa pun, `--force` membuang editan lokal pada file milik repo.

### Windows (native, tanpa WSL)

NTnRoute juga berjalan native di Windows melalui Git for Windows (bash MSYS2) — tanpa WSL.

1. Pasang [Git for Windows](https://git-scm.com/download/win) — sudah menyertakan `bash` dan `ssh` OpenSSH.
2. Buka **Git Bash**, lalu jalankan:

```bash
git clone https://github.com/Dandi41/ntnroute.git ~/ntnroute
cd ~/ntnroute
bash install.sh
```

Di Windows installer mendeteksi MSYS2 secara otomatis: engine terpasang di `~/.ntnroute/ntn`, `ntn` diletakkan di `~/.local/bin` sebagai salinan (symlink Windows butuh privilege), dan bila `jq` tidak ada ia mengunduh `jq.exe` ke `~/.ntnroute/bin` (engine menambahkan direktori itu ke `PATH` sendiri saat runtime). Bila shell tidak menemukan `ntn` setelah instalasi, tambahkan `~/.local/bin` ke PATH seperti saran installer. Semua command berperilaku sama seperti di Linux/macOS; sesi interaktif vendor berjalan lewat PTY MSYS2. Dukungan Windows sudah ada di branch utama.

## Mulai cepat

Jika bingung menggunakan engine NTnRoute, ketik `ntn` atau `ntn help` kepada agent. Agent akan menampilkan menu yang tersedia dan memandu alur kerja yang sesuai.

```bash
# daftarkan device (koneksi dites dulu; gagal = tidak disimpan)
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

# menu inventaris dan ringkasan konfigurasi
ntn list
ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]
ntn remove <number|id>
ntn show <ref>
ntn sync <ref|all>
```

Perubahan config selalu: rencana → persetujuan → apply → verifikasi. Skill `network-change-management` memaksa gerbang persetujuan dan membuat script rollback sebelum apa pun menyentuh device.

## Skill yang disertakan

| Skill | Fungsi |
|---|---|
| `ntnroute` | Aturan alur kerja inti engine `ntn` (inventaris, exec, config, rollback) |
| `network-device-cli` | Mekanika sesi SSH per vendor, kripto lawas, parsing kredensial |
| `network-change-management` | Gerbang rencana/persetujuan, pembuatan rollback |
| `network-troubleshooting` | Diagnosa OSI-first dengan referensi perintah vendor |
| `network-security-audit` | Audit hardening lokal + perimeter dari config device |

## Catatan keamanan

- Password disimpan **dalam plaintext** di `~/.ntnroute/devices.json` (mode 600, owner-only). Jaga baik-baik file tersebut agar tidak tersebar luas.
- `ntn show <ref>` tidak pernah menampilkan kredensial tersimpan — password hanya input transport.
- Backup config di `~/.ntnroute/backups/` memuat rahasia device yang sama — perlakukan dengan kehati-hatian yang sama.
## Status & kejujuran

Terbukti end-to-end di perangkat nyata: Cisco IOS 15.4 dan MikroTik RouterOS 7.18.2 (add/list/show/exec/sync, config + post-check, rollback, perintah destruktif, guard device tak terjangkau, guard error device). Brand lainnya (Huawei VRP, Arista EOS, Aruba AOS-CX, Ruijie RGOS, Juniper Junos, Fortinet FortiGate) diverifikasi dengan cara yang sama terhadap CLI vendor yang diemulasi (harness uji lokal, bukan bagian dari toolkit).

Jalur kode untuk Huawei, Aruba, Arista, Ruijie, dan Juniper ada tapi **belum** pernah diuji ke perangkat nyata — anggap eksperimental dan laporkan lewat Issues.

## Dukung

Kalau ntnroute membantu pekerjaanmu, kreator boleh dibelikan lemper 🙂: **[tako.id/Lemper41](https://tako.id/Lemper41)**

Temukan saya di [Instagram](https://www.instagram.com/sdandi_41/) dan [LinkedIn](https://www.linkedin.com/in/dandi-suryadi-a29276253/).

## Lisensi

[MIT](LICENSE) © Dandi Suryadi
