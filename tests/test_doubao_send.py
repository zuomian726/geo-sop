import unittest
from unittest.mock import Mock, patch

from platforms import doubao


class DoubaoSendTests(unittest.TestCase):
    def _editor(self, values):
        editor = Mock()
        editor.input_value.side_effect = list(values)
        return editor

    @patch.object(doubao, "_random_wait")
    def test_clicks_explicit_send_button_and_confirms_editor_cleared(self, _wait):
        page = Mock()
        button = Mock()
        button.is_visible.return_value = True
        button.is_enabled.return_value = True
        page.locator.return_value.first = button
        editor = self._editor(["问题", ""])

        doubao._verify_and_send(page, editor, "问题")

        button.click.assert_called_once_with()
        used_selectors = [call.args[0] for call in page.locator.call_args_list]
        self.assertNotIn("button:has(svg)", used_selectors)
        page.keyboard.press.assert_not_called()

    @patch.object(doubao, "_random_wait")
    def test_falls_back_to_enter_when_no_send_button_matches(self, _wait):
        page = Mock()
        button = Mock()
        button.is_visible.return_value = False
        page.locator.return_value.first = button
        editor = self._editor(["问题", ""])

        doubao._verify_and_send(page, editor, "问题")

        page.keyboard.press.assert_called_once_with("Enter")

    @patch.object(doubao, "_random_wait")
    def test_raises_actionable_error_when_question_remains_unsent(self, _wait):
        page = Mock()
        button = Mock()
        button.is_visible.return_value = False
        page.locator.return_value.first = button
        editor = self._editor(["问题", "问题"])

        with self.assertRaisesRegex(RuntimeError, "豆包问题未成功发送"):
            doubao._verify_and_send(page, editor, "问题")


if __name__ == "__main__":
    unittest.main()
