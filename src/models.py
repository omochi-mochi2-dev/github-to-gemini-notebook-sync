from dataclasses import dataclass
from typing import Literal, Optional
import hashlib

def format_tab_title(filename: str, max_length: int = 50) -> str:
    """フラットマッピング戦略に基づくタブ名の生成。
    50文字を超える場合はSHA-256ハッシュを利用して50文字に収める。"""
    base_name = filename.replace('/', '_').replace('.', '_')
    if len(base_name) <= max_length:
        return base_name
    
    file_hash = hashlib.sha256(filename.encode('utf-8')).hexdigest()
    return f"{base_name[:41]}_{file_hash[:8]}"

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
        return format_tab_title(self.filename)
