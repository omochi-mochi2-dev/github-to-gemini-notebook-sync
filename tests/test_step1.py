import unittest
from unittest.mock import patch, mock_open, MagicMock
import os
import yaml
import logging
import sys

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.models import FileDiff
from src.config import load_config
from src.github_client import (
    get_previous_commit_sha,
    fetch_commit_diffs,
    analyze_folder_rename,
    validate_failsafe
)

logging.basicConfig(level=logging.DEBUG)

MOCK_CONFIG_YAML = """
sync_targets:
  - repository: "microsoft/vscode-docs"
    watch_folders:
      - source_path: "docs/agents"
        google_doc_id: "DOC_ID_1"
        doc_name: "VSCode Agents Documentation"
"""

class TestStep1(unittest.TestCase):

    def test_filediff_target_tab_name(self):
        diff = FileDiff(
            filename="docs/agents/my_file.md",
            previous_filename=None,
            status="added",
            raw_content_url=None,
            commit_sha="sha123"
        )
        self.assertEqual(diff.target_tab_name, "docs_agents_my_file_md")

    @patch('os.environ.get')
    def test_load_config_success(self, mock_env):
        mock_env.return_value = 'fake_token'
        with patch('builtins.open', mock_open(read_data=MOCK_CONFIG_YAML)):
            with patch('os.path.exists', return_value=True):
                config = load_config('dummy.yaml')
                self.assertEqual(config['GITHUB_TOKEN'], 'fake_token')
                self.assertEqual(config['sync_targets'][0]['repository'], 'microsoft/vscode-docs')
                self.assertEqual(config['sync_targets'][0]['watch_folders'][0]['source_path'], 'docs/agents')

    @patch('os.environ.get')
    def test_load_config_missing_token(self, mock_env):
        mock_env.return_value = None
        with patch('builtins.open', mock_open(read_data=MOCK_CONFIG_YAML)):
            with patch('os.path.exists', return_value=True):
                with self.assertRaises(ValueError):
                    load_config('dummy.yaml')

    def test_get_previous_commit_sha(self):
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="abc123sha")):
                sha = get_previous_commit_sha('owner', 'repo')
                self.assertEqual(sha, "abc123sha")

    @patch('src.github_client.requests.get')
    def test_fetch_commit_diffs(self, mock_get):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "files": [
                {
                    "filename": "docs/file1.md",
                    "status": "added",
                    "raw_url": "url1"
                },
                {
                    "filename": "docs/file2.md",
                    "status": "unknown_status", # Should be mapped to modified
                    "raw_url": "url2"
                }
            ]
        }
        mock_get.return_value = mock_response

        diffs = fetch_commit_diffs("base", "head", "owner", "repo", "token")
        self.assertEqual(len(diffs), 2)
        self.assertEqual(diffs[0].status, "added")
        self.assertEqual(diffs[1].status, "modified")

    def test_analyze_folder_rename_success(self):
        diffs = [
            FileDiff(filename="new_docs/file1.md", previous_filename="docs/agents/file1.md", status="renamed", raw_content_url=None, commit_sha="123"),
            FileDiff(filename="new_docs/file2.md", previous_filename="docs/agents/file2.md", status="renamed", raw_content_url=None, commit_sha="123"),
        ]
        
        m_open = mock_open(read_data=MOCK_CONFIG_YAML)
        with patch('builtins.open', m_open):
            analyze_folder_rename(diffs, 'microsoft/vscode-docs', 'config.yaml')
            
            written_data = "".join(call.args[0] for call in m_open().write.mock_calls)
            self.assertIn("source_path: new_docs", written_data)

    def test_validate_failsafe_triggered(self):
        diffs = [
            FileDiff(filename="docs/agents/file1.md", previous_filename=None, status="removed", raw_content_url=None, commit_sha="123"),
            FileDiff(filename="docs/agents/file2.md", previous_filename=None, status="removed", raw_content_url=None, commit_sha="123"),
        ]
        
        with self.assertRaises(ValueError):
            validate_failsafe(diffs, "docs/agents")

    def test_validate_failsafe_not_triggered(self):
        diffs = [
            FileDiff(filename="docs/agents/file1.md", previous_filename=None, status="removed", raw_content_url=None, commit_sha="123"),
            FileDiff(filename="docs/agents/file2.md", previous_filename=None, status="modified", raw_content_url=None, commit_sha="123"),
        ]
        
        # Should not raise
        result = validate_failsafe(diffs, "docs/agents")
        self.assertTrue(result)

if __name__ == '__main__':
    unittest.main()
