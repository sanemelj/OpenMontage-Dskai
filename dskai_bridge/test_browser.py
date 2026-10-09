"""Real browser, SYNTHETIC records. No media generation."""
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

from dskai_bridge.app import create_app
from dskai_bridge.models import data
from dskai_bridge.store import Store
from dskai_bridge.test_bridge import shot


class BrowserTests(unittest.TestCase):
    def test_desktop_mobile_and_backlot(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp)/"state.db")
            credentials = {"director":"d"*32,"client":"c"*32,"worker":"w"*32}
            app = create_app(store, credentials, "http://127.0.0.1:4751", backlot=True)
            server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=4751, log_level="error"))
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            try:
                deadline = time.time()+10
                while not server.started:
                    if time.time()>deadline:
                        self.fail("studio failed to start")
                    time.sleep(.05)
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    try:
                        page = browser.new_page(viewport={"width":1440,"height":1000})
                        errors=[]
                        page.on("pageerror", lambda exc: errors.append(str(exc)))
                        page.goto("http://127.0.0.1:4751/studio/login")
                        page.locator("#password").fill(credentials["director"])
                        page.get_by_role("button", name="Sign in").click()
                        page.wait_for_url("**/studio")
                        page.get_by_text("No production requests yet.", exact=False).wait_for()
                        page.locator("#request-json").fill(json.dumps(data(shot())))
                        page.get_by_role("button", name="Record request", exact=True).click()
                        page.locator("article.shot").wait_for()
                        self.assertEqual(page.locator("article.shot").count(), 1)
                        page.get_by_role("button", name="Record request", exact=True).click()
                        page.wait_for_timeout(250)
                        self.assertEqual(page.locator("article.shot").count(), 1)
                        page.get_by_role("button", name="HOLD", exact=True).wait_for()
                        page.set_viewport_size({"width":390,"height":844})
                        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 390)
                        self.assertEqual(page.request.get("http://127.0.0.1:4751/api/health").status, 200)
                        self.assertFalse(errors, errors)
                        Path("test-artifacts").mkdir(exist_ok=True)
                        page.screenshot(path="test-artifacts/studio-mobile-synthetic.png", full_page=True)
                        page.set_viewport_size({"width":1440,"height":1000})
                        page.screenshot(path="test-artifacts/studio-desktop-synthetic.png", full_page=True)
                        page.get_by_role("button", name="Sign out").click()
                        page.wait_for_url("**/studio/login")
                        self.assertEqual(page.request.get("http://127.0.0.1:4751/api/projects").status, 401)
                        page.locator("#role").select_option("client")
                        page.locator("#password").fill(credentials["client"])
                        page.get_by_role("button", name="Sign in").click()
                        page.wait_for_url("**/studio")
                        page.locator("article.shot").wait_for()
                        self.assertTrue(page.locator("#submission").is_hidden())
                    finally:
                        browser.close()
            finally:
                server.should_exit = True
                thread.join(timeout=10)
