import unittest
from unittest.mock import patch

import cls_alert


class ClsAlertTests(unittest.TestCase):
    def test_matches_keywords_normalizes_spaces(self):
        item = {
            "title": "公司拟发行 H 股并提交上市申请",
            "content": "",
        }

        self.assertTrue(cls_alert.matches_keywords(item))

    def test_format_message_escapes_html(self):
        item = {
            "time": "12:00:00",
            "title": "A&B <test>",
            "content": "content <danger> & more",
        }

        message = cls_alert.format_message(item)

        self.assertIn("A&amp;B &lt;test&gt;", message)
        self.assertIn("content  &amp; more", message)

    def test_process_items_dry_run_does_not_save_state(self):
        items = [
            {
                "id": "1",
                "time": "12:00:00",
                "title": "上市申请",
                "content": "content",
            }
        ]

        with patch.object(cls_alert, "save_seen_ids") as save_seen_ids, patch.object(cls_alert.time, "sleep"):
            matched, sent = cls_alert.process_items(items, set(), dry_run=True, update_state=False)

        self.assertEqual(matched, 1)
        self.assertEqual(sent, 1)
        save_seen_ids.assert_not_called()


if __name__ == "__main__":
    unittest.main()
