# NTnRoute.AI

[English](README.md) | [Indonesia](README.id.md) | [Español](README.es.md) | [日本語](README.ja.md) | [Deutsch](README.de.md)

AIエージェント向けのSSHベース・ネットワーク機器エンジン：デバイスインベントリ、安全なCLI実行、コンフィグバックアップ、**承認ゲート付き**の設定変更と自動ロールバック。さらに、[Hermes Agent](https://hermes-agent.nousresearch.com)用のスキル群が、エージェントに責任ある使い方を教えます。

## できること

- **インベントリ** — デバイスを一度登録（`ntn add`）すると、エンジンがSSH接続をテストし、ホスト名とランニングコンフィグを取得してから保存します。保存先はプレーンなJSONファイル（`~/.ntnroute/devices.json`、パーミッション600）で、エージェントの再起動後も保持されます。
- **読み取り専用アクセス** — `ntn exec` が `show ...` 系コマンドを実行し、トランスクリプトを返します。
- **コンフィグバックアップ** — `ntn sync` がランニングコンフィグをインベントリとタイムスタンプ付きバックアップファイルに保存します。
- **ゲート付き設定変更** — `ntn config` は次を実行します：変更前スナップショット → 適用 → 保存 → ポストチェック（スクリプトの全行が新コンフィグに現れること） → インベントリ更新。変更前にデバイスに到達できない場合は中断。デバイスが行を拒否した場合は失敗を報告し、インベントリは変更しません。
- **ロールバック** — 変更ごとにチェックポイントを保存。`ntn rollback` で取り消しスクリプトを適用します。
- **監査ログ** — `ntn audit` が直近の操作を表示します。

Python不要、エージェント不要、デーモン不要。必要なのは **bash + jq + OpenSSH** だけです。

## 対応プラットフォーム

| ベンダー | モード | コンフィグ取得 | 保存 |
|---|---|---|---|
| Cisco IOS | 対話型PTY | `show running-config` | `write memory` |
| Huawei | 対話型PTY | `display current-configuration` | `commit` |
| Aruba / Arista / Ruijie / Juniper | 対話型PTY | ベンダー同等 | ベンダー保存 |
| MikroTik RouterOS | execモード（`ssh -T`） | `/export` | 自動 |

レガシー暗号（古いCiscoイメージ）にも対応：`diffie-hellman-group14-sha1`、`ssh-rsa`、`aes128-cbc`、`hmac-sha1` を必要に応じてネゴシエートします。

## インストール

要件：`bash`、`jq`、`ssh`（OpenSSH）のあるLinux/macOS。

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

## クイックスタート

```bash
# デバイスを登録（まず接続をテスト。失敗なら保存しない）
ntn add 10.0.0.5 22 admin S3cr3t! Router Cisco enablepass123

ntn list                # 番号付きインベントリ
ntn show 1              # 詳細 + 保存済みコンフィグ
ntn ping 1              # ICMPチェック
ntn exec 1 'show ip interface brief' 'show ip route'
ntn sync all            # 全デバイスのランニングコンフィグを取得
ntn audit 10            # 直近10操作
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

- パスワードは `~/.ntnroute/devices.json` に**平文**で保存されます（モード600、所有者のみ）。ラボツールとしての意図的なトレードオフです — 許容できない場合は本番環境に向けないでください。
- `ntn show <ref>` はデフォルトでパスワードをマスクします。`--reveal` で表示します。
- `devices.json` と `backups/` は .gitignore 済みです。**絶対にコミットしないでください。**

## ステータスと正直さ

実機でエンドツーエンド検証済み：Cisco IOS 15.4 と MikroTik RouterOS 7.18.2（add/list/show/exec/sync、config + ポストチェック、ロールバック、破壊的コマンド、到達不能デバイスのガード、デバイスエラーのガード）。

Huawei、Aruba、Arista、Ruijie、Juniper のコードパスは存在しますが、実機での検証は**まだ**です — 実験的とみなし、問題はIssuesで報告してください。

## ライセンス

[MIT](LICENSE) © Dandi Suryadi
