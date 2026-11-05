# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

AIエージェント向けのSSHベース・ネットワーク機器エンジン：デバイスインベントリ、安全なCLI実行、コンフィグバックアップ、**承認ゲート付き**の設定変更と自動ロールバック。さらに、[Hermes Agent](https://hermes-agent.nousresearch.com)用のスキル群が、エージェントに責任ある使い方を教えます。

## できること

- **インベントリ** — デバイスを一度登録（`ntn add`）すると、エンジンがSSH接続をテストし、ホスト名とランニングコンフィグを取得してから保存します。保存先はプレーンなJSONファイル（`~/.ntnroute/devices.json`、パーミッション600）で、エージェントの再起動後も保持されます。
- **読み取り専用アクセス** — エンジンが `show ...` 系コマンドを要求に応じて実行し、トランスクリプトを返します。
- **コンフィグバックアップ** — `ntn sync` がランニングコンフィグをインベントリとタイムスタンプ付きスナップショットとして保存します。成功した変更（およびロールバック）ごとに `~/.ntnroute/backups/<host>/<YYYY-MM>/` へアーカイブペアが公開されます。各月フォルダには変更ペア最大4件とsync/addスナップショット最大4件が入り、直近3ヶ月＋年1件が保持されます。旧バージョンの散在ファイルは自動的にこのレイアウトへ移動されます。
- **ゲート付き設定変更** — `ntn config` は次を実行します：変更前スナップショット → 適用 → 保存 → インベントリ／アーカイブ更新。デバイス側のコマンドエラー、セッション切断、変更前スナップショットの取得不能の場合だけ失敗します。機能的な成功は、その後に計画済みの読み取り専用チェックで確認します。
- **ロールバック** — 変更ごとにチェックポイントを保存。保存された取り消しスクリプトは要求に応じて再生できます。
- **監査ログ** — config/rollback の試行はデバイスに触れる*前*に記録され（`config-pending`）、その後確定します：`config-ok`/`config-failed`/`config-aborted` と、記録用の `config-started` マーカー。変更ログのフィルタはトラブルシュートとセキュリティ監査向け：`pending`（判定が一切ない試行 — apply 中にプロセスが停止）、`failed`、`config`、`all`。 105日より古いエントリは自動で削除されます。セキュリティ監査の実行記録は別に保存され、実際に監査を行ったときだけ書き込まれます。

エンジンは bash + jq + OpenSSH のみ。Pythonもエージェントもデーモンも不要です。
ヘルパースクリプト（`triage`、`rollback_gen`、`ios_session.sh`）も bash + awk。
Python（標準ライブラリのみ）を使うのは任意の監査ゲート（`cfg_audit.py`、
`sec_audit.py`）だけです。

## 対応プラットフォーム

| ベンダー | モード | コンフィグ取得 | 保存 |
|---|---|---|---|
| Cisco IOS | 対話型PTY | `show running-config` | `write memory` |
| Huawei VRP | 対話型PTY | `display current-configuration` | `save` + 確認 |
| Aruba / Arista / Ruijie | 対話型PTY | `show running-config` | `write memory` |
| Juniper Junos | 対話型PTY | `show configuration \| display set` | `commit`（設定モード内で実行） |
| Fortinet FortiGate | 対話型PTY | `show full-configuration` | 自動（入力時に即反映） |
| MikroTik RouterOS | execモード（`ssh -T`） | `/export verbose` | 自動 |
| Linux（SSH） | execモード（`ssh -T`） | `uname -a`＋os-release のスナップショット | —（コンフィグモデルなし） |
| Windows（OpenSSH、cmd.exe） | exec-arg（`ssh host "cmd"`） | `systeminfo` のスナップショット | —（コンフィグモデルなし） |

レガシー暗号（古いCiscoイメージ）にも対応：`diffie-hellman-group14-sha1`、`ssh-rsa`、`aes128-cbc`、`hmac-sha1` を必要に応じてネゴシエートします。

## 新しいベンダーへの適応

ブランドごとの動作は `~/.ntnroute/brands.json` にあります — エンジンが知らないベンダーへの対応や、組み込みの上書き（ファームウェアの変更含む）はこのファイルの編集で行えます。1エントリで十分です：

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

フィールド：`paging`、`secret_cmd`、`config_enter`、`config_leave`、`save_lines`（配列）、`save_delay`、`config_show`、`hostname_show`、`hostname_field`（`hostname`|`sysname`|`host-name`|`colon`）、`err_pattern`（grep -E）、`negate_prefix`（`rollback_gen` が使用）。プロファイルのない未知のブランドは Cisco 風のジェネリック既定値を使い、保存ステップを省略します。インストーラはあなたの `brands.json` を上書きしません。

## デバイスデータベースの形式

インベントリは `~/.ntnroute/devices.json` に保存されます（モード600、gitignore対象 — 本物のファイルをコミットしないでください）。エンジンは決まった形式を読み書きします：`next_id`、`devices[]`、`checkpoints[]`、`audit[]`、`security_audits[]`。プレースホルダーの認証情報で埋めた参照例は [`examples/devices.example.json`](examples/devices.example.json) を見てください — AIエージェントやスクリプトにはこのファイルを指し示し、独自の項目名をでっち上げないようにします。

## インストール

要件：`bash`、`jq`、`ssh`（OpenSSH）のあるLinux/macOS、または Windows（Git for Windows 経由）。macOS は GNU coreutils（`brew install coreutils`）が必要です。

```bash
git clone https://github.com/Dandi41/ntnroute.git
cd ntnroute
./install.sh
```

インストーラは：

1. `jq` と `ssh` を確認し、
2. エンジンを `~/.ntnroute/ntn`（モード700）にインストールし、`~/.local/bin/ntn` にシンボリックリンクを作成し、
3. 空のインベントリ（モード600）で `~/.ntnroute/` を作成し、
4. [Hermes Agent](https://hermes-agent.nousresearch.com) を使っている場合は、5つのスキルを `~/.hermes/skills/networking/` にコピーします。

### Windows（ネイティブ、WSL 不要）

NTnRoute は Git for Windows（MSYS2 bash）経由で Windows でもネイティブに動作します — WSL は不要です。

1. [Git for Windows](https://git-scm.com/download/win) をインストール（`bash` と OpenSSH の `ssh` 同梱）。
2. **Git Bash** を開いて実行：

```bash
git clone -b beta https://github.com/Dandi41/ntnroute.git ~/ntnroute
cd ~/ntnroute
bash install.sh
```

Windows ではインストーラーが MSYS2 を自動検出します：エンジンは `~/.ntnroute/ntn` に、`ntn` はコピーとして `~/.local/bin` に置かれ（Windows のシンボリックリンクには権限が必要）、`jq` が無ければ `jq.exe` を `~/.ntnroute/bin` にダウンロードします（エンジンが実行時に自前でそのディレクトリを `PATH` に追加）。インストール後にシェルが `ntn` を見つけられない場合は、インストーラーの案内どおり `~/.local/bin` を PATH に追加してください。すべてのコマンドは Linux/macOS と同じように動作し、ベンダーとの対話セッションは MSYS2 の PTY を使います。Windows 対応は `beta` ブランチにあります（マージまで）。

## クイックスタート

NTnRoute エンジンの使い方が分からない場合は、agent に `ntn` または `ntn help` と入力してください。agent が利用可能なメニューを表示し、適切なワークフローを案内します。

```bash
# デバイスを登録（まず接続をテスト。失敗なら保存しない）
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

# インベントリおよび設定概要メニュー
ntn list
ntn add <IP> <Port> <User> <Pass> <Type> <Brand> [Secret]
ntn remove <number|id>
ntn show <ref>
ntn sync <ref|all>
```

設定変更は常に：計画 → 承認 → 適用 → 検証。同梱の `network-change-management` スキルが承認ゲートを強制し、デバイスに触れる前にロールバックスクリプトを生成します。

## 同梱スキル

| スキル | 目的 |
|---|---|
| `ntnroute` | `ntn` エンジンのコアワークフロールール（インベントリ、exec、config、ロールバック） |
| `network-device-cli` | ベンダー別SSHセッションの仕組み、レガシー暗号、認証情報の解析 |
| `network-change-management` | 計画/承認ゲート、影響範囲（ブラスト半径）監査、ロールバック生成 |
| `network-troubleshooting` | OSIファーストの診断とベンダー別コマンドリファレンス |
| `network-security-audit` | デバイスコンフィグのローカル強化 + ペリメータ監査 |

## セキュリティに関する注意

- パスワードは `~/.ntnroute/devices.json` に**平文**で保存されます（モード600、所有者のみ）。ファイルがマシンの外に広がらないよう、厳重に管理してください。
- `ntn show <ref>` はデフォルトでパスワードをマスクします。
- `~/.ntnroute/backups/` のコンフィグバックアップにも同じデバイスの秘密が含まれます — 同様に慎重に扱ってください。
## ステータスと正直さ

実機でエンドツーエンド検証済み：Cisco IOS 15.4 と MikroTik RouterOS 7.18.2（add/list/show/exec/sync、config + ポストチェック、ロールバック、破壊的コマンド、到達不能デバイスのガード、デバイスエラーのガード）。その他のブランド（Huawei VRP、Arista EOS、Aruba AOS-CX、Ruijie RGOS、Juniper Junos、Fortinet FortiGate）は、エミュレートしたベンダーCLIに対して同じ手順で検証しています（ローカルのテストハーネスで、ツールキットには含まれません）。

Huawei、Aruba、Arista、Ruijie、Juniper のコードパスは存在しますが、実機での検証は**まだ**です — 実験的とみなし、問題はIssuesで報告してください。

## サポート

ntnroute が役に立ったら、作者にレンペル（インドネシアの餅米スナック）を奢ってあげてください 🙂：**[tako.id/Lemper41](https://tako.id/Lemper41)**

[Instagram](https://www.instagram.com/sdandi_41/) と [LinkedIn](https://www.linkedin.com/in/dandi-suryadi-a29276253/) もやっています。

## ライセンス

[MIT](LICENSE) © Dandi Suryadi
