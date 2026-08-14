import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Ensure src can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.models import FileDiff
from src.docs_client import (
    extract_tabs_info,
    generate_sync_payload
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

    def test_extract_tabs_info(self):
        info = extract_tabs_info(self.mock_doc_state)
        self.assertIn("docs_agents_test1_md", info)
        self.assertEqual(info["docs_agents_test1_md"]["tabId"], "TAB123")
        self.assertEqual(info["docs_agents_test1_md"]["endIndex"], 50)

    def test_generate_sync_payload_atomic_update(self):
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
    
        create_requests, update_requests = generate_sync_payload(diffs, self.mock_doc_state, file_contents)
    
        self.assertEqual(len(create_requests), 0)
        # We expect 2 requests: deleteContentRange and insertText
        self.assertEqual(len(update_requests), 2)
    
        # First request should be deleteContentRange
        self.assertIn("deleteContentRange", update_requests[0])
        self.assertIn("insertText", update_requests[1])
        self.assertEqual(update_requests[0]["deleteContentRange"]["range"]["startIndex"], 1)
        self.assertEqual(update_requests[0]["deleteContentRange"]["range"]["endIndex"], 500000)
        self.assertEqual(update_requests[0]["deleteContentRange"]["range"]["tabId"], "TAB123")

        # Second request should be insertText at index 1
        self.assertIn("insertText", update_requests[1])
        self.assertEqual(update_requests[1]["insertText"]["location"]["index"], 1)
        self.assertEqual(update_requests[1]["insertText"]["location"]["tabId"], "TAB123")
        self.assertEqual(update_requests[1]["insertText"]["text"], "Hello World!")

    def test_generate_sync_payload_add_new_tab(self):
        diffs = [
            FileDiff(
                filename="docs/agents/new_file.md",
                previous_filename=None,
                status="added",
                raw_content_url="url",
                commit_sha="sha"
            )
        ]
        file_contents = {
            "docs/agents/new_file.md": "New content"
        }
    
        create_requests, update_requests = generate_sync_payload(diffs, self.mock_doc_state, file_contents)
    
        self.assertEqual(len(create_requests), 1)
        self.assertIn("createTab", create_requests[0])
        self.assertEqual(len(update_requests), 0)
        self.assertEqual(create_requests[0]["createTab"]["title"], "docs_agents_new_file_md")

    def test_generate_sync_payload_remove_tab(self):
        diffs = [
            FileDiff(
                filename="docs/agents/old.md",
                previous_filename=None,
                status="removed",
                raw_content_url="url",
                commit_sha="sha"
            ),
            FileDiff(
                filename="docs/agents/test1.md",
                previous_filename=None,
                status="modified", # Mix with modified to prevent failsafe
                raw_content_url="url",
                commit_sha="sha"
            )
        ]
    
        create_requests, update_requests = generate_sync_payload(diffs, self.mock_doc_state, {})
    
        self.assertEqual(len(create_requests), 0)
        # Should have 1 deleteTab and 1 deleteContentRange (since file_contents is empty, no insertText)
        self.assertEqual(len(update_requests), 2)
        self.assertIn("deleteTab", update_requests[0])
        self.assertIn("deleteContentRange", update_requests[1])
        self.assertEqual(update_requests[0]["deleteTab"]["tabId"], "TAB999")

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
            generate_sync_payload(diffs, self.mock_doc_state, {})
            
        self.assertIn("Fail-safe", str(context.exception))

if __name__ == '__main__':
    unittest.main()
