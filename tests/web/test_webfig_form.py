"""Local Chromium tests only; never connects to devices."""
import unittest


class FormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise unittest.SkipTest('optional Playwright unavailable') from None
        cls.runtime = sync_playwright().start()
        try:
            cls.browser = cls.runtime.chromium.launch(headless=True)
        except Exception:
            cls.runtime.stop()
            raise unittest.SkipTest('Chromium unavailable; tests do not install browsers') from None

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.runtime.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.set_content('''<div id="content"><table><tr>
        <td class="label">Enabled</td><td><input type="checkbox" checked></td>
        </tr></table><button onclick="window.submitted=true">OK</button></div>
        <script>window.changes=0;document.addEventListener('change',e=>{
        if(e.target.type==='checkbox'){window.changes++;let checked=e.target.checked;
        setTimeout(()=>{let n=e.target.cloneNode();n.checked=checked;e.target.replaceWith(n)},10)}})</script>''')

    def tearDown(self):
        self.page.close()

    def test_native_change_rerender_and_no_submit(self):
        from web.webfig_form import set_draft_checkbox, read_checkbox
        set_draft_checkbox(self.page, 'Enabled', False)
        self.assertFalse(read_checkbox(self.page, 'Enabled'))
        self.assertEqual(self.page.evaluate('window.changes'), 1)
        self.assertIsNone(self.page.evaluate('window.submitted'))
        set_draft_checkbox(self.page, 'Enabled', False)
        self.assertEqual(self.page.evaluate('window.changes'), 1)

    def test_missing_hidden_duplicate_and_disabled_fail(self):
        from web.webfig_form import set_draft_checkbox
        for expression in [
            "document.querySelector('tr').remove()",
            "document.querySelector('tr').style.display='none'",
            "document.querySelector('table').append(document.querySelector('tr').cloneNode(true))",
            "document.querySelector('input').disabled=true",
        ]:
            with self.subTest(expression=expression):
                original=self.page.content()
                self.page.evaluate(expression)
                with self.assertRaises(ValueError):
                    set_draft_checkbox(self.page, 'Enabled', False)
                self.page.set_content(original)

    def test_reverted_state_fails_not_retried(self):
        from web.webfig_form import set_draft_checkbox
        self.page.evaluate("document.addEventListener('change',e=>setTimeout(()=>{document.querySelector('input').checked=true},30))")
        with self.assertRaises(ValueError):
            set_draft_checkbox(self.page, 'Enabled', False)
        self.assertEqual(self.page.evaluate('window.changes'), 1)
