import os
import logging
from typing import Dict, Any, List, Tuple
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.models import FileDiff

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/documents']

def init_docs_client(credentials_path: str = 'credentials.json') -> Any:
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

def fetch_document_tabs(service: Any, document_id: str) -> Dict[str, Any]:
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
    FileDiffのリストを受け取り、既存のタブの中身を更新するための
    documents.batchUpdate用ペイロードを生成する関数。
    API経由でのタブの作成・削除は未サポートのため、存在しないタブや削除リクエストはWarningを出力してスキップする。
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
            logger.warning(f"Skipping deletion for '{target_tab_name}': API does not support deleting tabs. Please delete it manually.")
            continue
                
        elif diff.status in ['added', 'modified', 'renamed']:
            if target_tab_name not in tab_info_map:
                logger.warning(f"Skipping update for '{target_tab_name}': Tab does not exist. Please create it manually.")
                continue
            else:
                # 存在する場合は既存コンテンツを削除して新規テキストを挿入
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
