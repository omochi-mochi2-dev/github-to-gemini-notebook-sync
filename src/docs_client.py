import os
import logging
from typing import Dict, Any, List
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.models import FileDiff

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/documents']

def init_docs_client(credentials_path: str = 'credentials.json'):
    """
    credentials.json を使用して、Google Docs APIクライアントの認証初期化を行う。
    """
    if not os.path.exists(credentials_path):
        logger.error(f"Credentials file not found: {credentials_path}")
        raise FileNotFoundError(f"Credentials file not found: {credentials_path}")
        
    try:
        credentials = Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES)
        service = build('docs', 'v1', credentials=credentials)
        logger.info("Google Docs API client initialized successfully.")
        return service
    except Exception as e:
        logger.error(f"Failed to initialize Google Docs API client: {e}")
        raise

def fetch_document_tabs(service, document_id: str) -> Dict[str, Any]:
    """
    documents.get を呼び出し、パラメータとして includeTabsContent=true を明示的に指定して
    既存のタブ一覧とコンテンツを含むドキュメント構造を取得する。
    """
    logger.info(f"Fetching document tabs for document ID: {document_id}")
    try:
        doc = service.documents().get(
            documentId=document_id,
            includeTabsContent=True
        ).execute()
        return doc
    except HttpError as e:
        logger.error(f"Google Docs API HTTP Error fetching document {document_id}: {e}")
        raise

def extract_tabs_info(document_content: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    取得したドキュメント構造からタブ名とtabId、および現在のendIndexを抽出するユーティリティ関数。
    戻り値は { "tab_title": {"tabId": "...", "endIndex": 123} } の辞書。
    """
    tab_info_map = {}
    tabs = document_content.get('tabs', [])
    for tab in tabs:
        tab_props = tab.get('tabProperties', {})
        tab_id = tab_props.get('tabId')
        title = tab_props.get('title')
        
        # Calculate end_index (length of the content)
        end_index = 2
        try:
            body_content = tab.get('documentTab', {}).get('body', {}).get('content', [])
            if body_content:
                end_index = body_content[-1].get('endIndex', 2)
        except Exception as e:
            logger.warning(f"Could not determine end index for tab {title}: {e}")
            
        if tab_id and title:
            tab_info_map[title] = {
                'tabId': tab_id,
                'endIndex': end_index
            }
            
    return tab_info_map

def generate_sync_payload(diffs: List[FileDiff], doc_state: Dict[str, Any], file_contents: Dict[str, str]) -> List[Dict[str, Any]]:
    """
    FileDiffのリストを受け取り、フラットマッピング戦略に従ってタブの追加、更新、削除を行うための
    documents.batchUpdate用ペイロードを生成する関数。
    """
    requests = []
    tab_info_map = extract_tabs_info(doc_state)

    if diffs and all(diff.status == 'removed' for diff in diffs):
        logger.error("Fail-safe triggered: All detected diffs are 'removed'. Aborting sync to prevent total document deletion.")
        raise RuntimeError("Fail-safe: 監視対象パス内の全ファイルが削除対象になっています。不正な全削除を防ぐため処理を中断します。")

    for diff in diffs:
        target_tab_name = diff.target_tab_name
        content = file_contents.get(diff.filename, "")
        
        if diff.status == 'removed':
            if target_tab_name in tab_info_map:
                tab_id = tab_info_map[target_tab_name]['tabId']
                requests.append({
                    "deleteTab": {
                        "tabId": tab_id
                    }
                })
            else:
                logger.warning(f"Tab {target_tab_name} not found for deletion. Skipping.")
                
        elif diff.status in ['added', 'modified', 'renamed']:
            # 新規タブ作成
            if target_tab_name not in tab_info_map:
                requests.append({
                    "createTab": {
                        "title": target_tab_name
                    }
                })
                # 新規作成タブへのコンテンツ挿入は、tabIdが直ちに確定しないため
                # この実装では別途(または次回実行時に)行われる想定か、
                # あるいは createTab はレスポンスなしに後続リクエストで参照できない制約がある。
                # ここでは要件通り「追加」リクエストを生成。
                
            else:
                # 既存タブの更新: docs_tabs_logic.md に準拠したアトミック更新のシンプル化
                tab_id = tab_info_map[target_tab_name]['tabId']
                
                # ① 先に既存コンテンツを全削除（大きな endIndex で安全に全範囲を指定）
                requests.append({
                    "deleteContentRange": {
                        "range": {
                            "startIndex": 1,
                            "endIndex": 500000,
                            "tabId": tab_id
                        }
                    }
                })
                
                # ② インデックス 1 の位置から新規テキストを挿入
                if content:
                    requests.append({
                        "insertText": {
                            "location": {
                                "index": 1,
                                "tabId": tab_id
                            },
                            "text": content
                        }
                    })
                    
    return requests
