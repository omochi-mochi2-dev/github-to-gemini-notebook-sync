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
