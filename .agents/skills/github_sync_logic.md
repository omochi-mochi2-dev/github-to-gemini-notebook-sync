# Skill: GitHub Compare API & Delta Detection

## 概要

このスキルは、GitHub REST APIを用いて2つのコミット間の変更（差分）を検知し、安全に同期対象ファイルを特定するためのドメイン知識を提供します。

## 重要なドメイン知識と処理ロジック

- **比較エンドポイント**: `GET /repos/{owner}/{repo}/compare/{base}...{head}` を使用する。
- **ステートフル差分検知**: `actions/cache` で永続化した前回実行時のコミットSHA（`last_commit_sha.txt`）を `base`、最新コミットを `head` として比較し、最小限の差分のみを取得する。
- **自己修復（フォルダ移動検知）**:
  - ファイルの `status` が `renamed` である場合、`previous_filename` 属性を取得できる。
  - 監視対象ディレクトリ配下のファイルの一定割合（例: 80%以上）が同時にリネームされている場合、ルートフォルダ自体の移動と判断し、`config.yaml` の監視パスを動的に書き換えて追従すること。
  - 移動先が特定できないなどの異常時は、処理を中断（フェイルセーフ）し、GitHub Actionsをエラー終了させてアラートを送信すること。
