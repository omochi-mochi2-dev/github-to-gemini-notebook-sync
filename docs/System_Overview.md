# System Overview: GitHub ↔ Google Docs Sync System

## 1. システム目的と概要

本システムは、GitHubリポジトリ内の特定フォルダ（`docs/agents` や `docs/agent-customization` 等）のMarkdownドキュメントの更新・差分を自動検知し、Google Docs APIのTabs機能を経由してGoogleドキュメント（Gemini Notebook参照用）へ自律同期するシステムです。

---

## 2. System Architecture

- **実行環境**: GitHub Actions（スケジュールトリガー / cronによる定期実行）
- **差分検出**: `actions/cache` を用いて前回のコミットSHA（`last_commit_sha.txt`）を保持し、GitHub Compare APIで差分ファイルのみを抽出するステートフル同期
- **ターゲット構成**: 1つの監視対象フォルダにつき1つのGoogleドキュメントを割り当て、配下のファイルをタブ（Tabs）として同期

---

## 3. AIエージェントへの絶対的制約 (Guardrails)

### ① フラットマッピング戦略（Flat Mapping Strategy）

- **制約**: Google Docs上で子タブ（ネストされたタブ構造）は**絶対に作成しないこと**。
- **理由**: Gemini Notebookの仕様上、子タブ内のコンテンツはRAG解析時に正常に読み込まれないため。
- **命名規則**: ディレクトリの相対パス構造（例: `src/auth/login.md`）は、アンダースコアやスラッシュ置換を用いたフラットな第1階層のタブ名（例: `src_auth_login`）として作成すること。

### ② 技術スタックとコード品質

- Python 3.10 以上および公式SDK（`google-api-python-client` 等）を使用すること。
- 全ての関数に型ヒント（Type Hints）を記述し、`logging` モジュールによる適切なエラーハンドリングを行うこと。

---

## 4. 自己修復・フォールトトレランス設計とアラート

- **移動・リネーム検知（自己修復）**: 監視対象フォルダ自体が移動・リネームされた場合、GitHub Compare APIの `status: "renamed"` および `previous_filename` を検知し、自動的に `config.yaml` の監視パスを書き換えて追従する自己修復ロジックを備えること。
- **完全消失時のフェイルセーフと緊急アラート**: 対象フォルダ内の全ファイルが `removed` ステータスとなり完全に消失した場合、または移動先が特定できない異常状態に陥った場合は、**「予期せぬ破壊的変更」とみなし、即座に処理を中断（フェイルセーフ）すること。** 誤ってGoogleドキュメントのコンテンツをすべて空にする破壊的更新を絶対に防ぐこと。
- **アラート発報**: フェイルセーフ発動時は、GitHub Actionsをエラー終了（Exit 1）させ、ステップサマリーへのエラー出力、またはリポジトリへの自動Issue作成を通じて管理者に緊急アラート通知を送信するフローを確立すること。
