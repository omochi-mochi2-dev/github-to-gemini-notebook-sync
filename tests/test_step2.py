import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.models import FileDiff
from src.docs_client import (
    extract_tabs_info,
    generate_phase1_payload,
    generate_phase2_payload
)

class TestStep2(unittest.TestCase):

    def setUp(self):
        self.mock_doc_state = {
            "tabs": [
                {
                    "tabProperties": {
                        "tabId": "TAB123",
                        "title": "docs_agents_test1_md"
                    },
                    "documentTab": {
                        "body": {
                            "content": [
                                {"endIndex": 1},
                                {"endIndex": 50}
                            ]
                        }
                    }
                },
                {
                    "tabProperties": {
                        "tabId": "TAB999",
                        "title": "docs_agents_old_md"
                    },
                    "documentTab": {
                        "body": {
                            "content": [
                                {"endIndex": 100}
                            ]
                        }
                    }
                }
            ]
        }
        self.mock_tab_info = extract_tabs_info(self.mock_doc_state)

    def test_extract_tabs_info(self):
        self.assertIn("docs_agents_test1_md", self.mock_tab_info)
        self.assertEqual(self.mock_tab_info["docs_agents_test1_md"]["tabId"], "TAB123")
        self.assertEqual(self.mock_tab_info["docs_agents_test1_md"]["endIndex"], 50)

    def test_generate_phase1_payload(self):
        diffs = [
            FileDiff(
                filename="docs/agents/new_file.md",
                previous_filename=None,
                status="added",
                raw_content_url="url",
                commit_sha="sha"
            ),
            FileDiff(
                filename="docs/agents/old.md",
                previous_filename=None,
                status="removed",
                raw_content_url="url",
                commit_sha="sha"
            )
        ]
        
        requests = generate_phase1_payload(diffs, self.mock_tab_info)
        
        self.assertEqual(len(requests), 2)
        # Expected: addDocumentTab for new_file.md, deleteTab for old.md
        self.assertIn("addDocumentTab", requests[0])
        self.assertEqual(requests[0]["addDocumentTab"]["tabProperties"]["title"], "docs_agents_new_file_md")
        self.assertIn("deleteTab", requests[1])
        self.assertEqual(requests[1]["deleteTab"]["tabId"], "TAB999")

    def test_generate_phase2_payload(self):
        diffs = [
            FileDiff(
                filename="docs/agents/test1.md",
                previous_filename=None,
                status="modified",
                raw_content_url="url",
                commit_sha="sha"
            )
        ]
        file_contents = {
            "docs/agents/test1.md": "Hello World!"
        }
        
        requests = generate_phase2_payload(diffs, self.mock_tab_info, file_contents)
        
        # Expected: deleteContentRange, insertText
        self.assertEqual(len(requests), 2)
        self.assertIn("deleteContentRange", requests[0])
        self.assertEqual(requests[0]["deleteContentRange"]["range"]["tabId"], "TAB123")
        self.assertEqual(requests[0]["deleteContentRange"]["range"]["startIndex"], 1)
        self.assertEqual(requests[0]["deleteContentRange"]["range"]["endIndex"], 500000)
        
        self.assertIn("insertText", requests[1])
        self.assertEqual(requests[1]["insertText"]["location"]["tabId"], "TAB123")
        self.assertEqual(requests[1]["insertText"]["location"]["index"], 1)
        self.assertEqual(requests[1]["insertText"]["text"], "Hello World!")

    def test_failsafe_triggered(self):
        diffs = [
            FileDiff(
                filename="docs/agents/old.md",
                previous_filename=None,
                status="removed",
                raw_content_url="url",
                commit_sha="sha"
            )
        ]
        
        with self.assertRaises(RuntimeError) as context:
            generate_phase1_payload(diffs, self.mock_tab_info)
            
        self.assertIn("Fail-safe", str(context.exception))

    def test_generate_phase1_payload_renamed(self):
        diffs = [
            FileDiff(
                filename="docs/agents/new_renamed.md",
                previous_filename="docs/agents/old.md",
                status="renamed",
                raw_content_url="url",
                commit_sha="sha"
            )
        ]
        
        requests = generate_phase1_payload(diffs, self.mock_tab_info)
        
        self.assertEqual(len(requests), 2)
        # Expected: addDocumentTab for new_renamed.md
        self.assertIn("addDocumentTab", requests[0])
        self.assertEqual(requests[0]["addDocumentTab"]["tabProperties"]["title"], "docs_agents_new_renamed_md")
        
        # Expected: deleteTab for old.md (TAB999 in mock)
        self.assertIn("deleteTab", requests[1])
        self.assertEqual(requests[1]["deleteTab"]["tabId"], "TAB999")

if __name__ == '__main__':
    unittest.main()
