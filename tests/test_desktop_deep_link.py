import sys
import unittest
from unittest.mock import patch

import desktop_app


class DesktopDeepLinkTests(unittest.TestCase):
    def startup_path(self, url: str) -> str:
        with patch.object(sys, "argv", ["GEO-SOP", url]):
            return desktop_app._startup_path_from_args()

    def test_platform_login_link_opens_login_workflow(self):
        self.assertEqual(
            "/dashboard?open=platform-login",
            self.startup_path("geo-sop://open?target=login"),
        )

    def test_ai_settings_link_opens_sentiment_settings(self):
        self.assertEqual(
            "/dashboard?open=ai-settings#sentiment_settings",
            self.startup_path("geo-sop://open?target=ai-settings"),
        )

    def test_unknown_link_is_restricted_to_dashboard(self):
        self.assertEqual(
            "/dashboard",
            self.startup_path("geo-sop://open?target=https%3A%2F%2Fevil.example"),
        )


if __name__ == "__main__":
    unittest.main()
