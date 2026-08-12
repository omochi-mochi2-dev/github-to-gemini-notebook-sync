# Detailed Logic & Data Models: GitHub ↔ Google Docs Sync System

## 1. Pythonデータモデル定義（データ構造の強制）

モジュール間（GitHub API層 ↔ Google Docs API層）でのデータ受け渡しには、以下の `dataclass` を厳密に使用すること。AIエージェントによる独自のプロパティの追加・変更は許可しない。

```python
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class FileDiff:
    filename: str
    previous_filename: Optional[str]
    status: Literal['added', 'modified', 'removed', 'renamed']
    raw_content_url: Optional[str]
    commit_sha: str

    @property
    def target_tab_name(self) -> str:
        """フラットマッピング戦略に基づくタブ名の生成"""
        # フォルダ構造の階層 (/) や拡張子をアンダースコアに置換しフラットな第一階層タブ名を作成
        return self.filename.replace('/', '_').replace('.', '_')
```

---

## 2. GitHub Compare API の解析要件

- **APIエンドポイント**: `GET /repos/{owner}/{repo}/compare/{base}...{head}`
- **処理ロジック**:
  - `last_commit_sha.txt` に記録された前回実行時のコミットSHAを `base`、現在の最新コミットSHA（HEAD）を `head` として比較を実行する。
  - レスポンスの `files` 配列をループ処理し、上記定義の `FileDiff` オブジェクトのリストを生成する。

---

## 3. Google Docs API 更新ロジックの厳格な仕様

Google Docs APIは、インデックスが狂うことによるドキュメントの破壊を防ぐため、以下のロジック仕様を徹底すること。

### ① タブ構造の完全取得

- `documents.get` メソッド呼び出し時は、必ずパラメータとして **`includeTabsContent=true`** を明示的に指定すること。
- これを怠ると、下位互換性のために最初のタブしか読み込まれず、他のタブ情報が完全に隠蔽（サイレントに無視）されてしまう。

### ② 後方からの処理（Write Backwards）戦略

- 複数のテキスト挿入や削除を一度に行う場合、インデックスのズレ（文字数がずれて意図しない場所を削除・上書きすること）を防ぐため、ドキュメントの末尾（インデックスの大きい方）から先頭に向かって逆順に処理（Write Backwards）を行うロジックを構築すること。

### ③ アトミックな更新処理（削除 & 挿入）

- 同一タブ内のコンテンツを更新（上書き）する際、**既存テキストの全範囲の削除（`deleteContentRange`）** と **新規テキストの挿入（`insertText`）** を、`documents.batchUpdate` 内の同一リクエストリスト（Requests配列）にまとめて**アトミックに送信・実行**すること。
- リクエストオブジェクトの `Location` オブジェクトには、必ず対象の **`tabId`** を指定すること。

### ④ APIペイロード（リクエスト）の構造例

以下の構造に従って `documents.batchUpdate` のリクエストを組み立てること。

```json
{
  "requests": [
    {
      "deleteContentRange": {
        "range": {
          "startIndex": 1,
          "endIndex": 500000,
          "tabId": "TAB_ID_HERE"
        }
      }
    },
    {
      "insertText": {
        "location": {
          "index": 1,
          "tabId": "TAB_ID_HERE"
        },
        "text": "# ここに新規テキストが挿入されます\n\nMarkdownのプレーンテキストが入ります。"
      }
    }
  ]
}
```

---

## 4. GitHub Actions ワークフロー自動化要件

- **トリガー**: `schedule` (cronによる1時間ごとの定期実行) および手動実行用の `workflow_dispatch`。
- **状態管理**: `actions/cache` を使用し、同期を完了したGitのコミットハッシュ（`last_commit_sha.txt`）をキャッシュとして永続化・管理する。キャッシュキーは `sync-sha-${{ github.run_id }}` などの動的なバリエーションを設定すること。
