import unittest
from pathlib import Path
import tomllib
from unittest.mock import MagicMock, patch

from gdo.base.Application import Application
from gdo.base.Trans import Trans
from gdo.counter.module_counter import module_counter


class PagecountTest(unittest.TestCase):
    def test_setting_is_optional_and_priority_is_100(self):
        module = module_counter()
        setting = module.gdo_module_config()[0]
        self.assertEqual('counter_pagecount', setting.get_name())
        self.assertIsNone(setting.get_val())
        self.assertFalse(setting.is_not_null())
        self.assertEqual(100, module._priority)

    def test_get_counted_once_and_displayed_for_each_position(self):
        for position, bar in module_counter.PAGE_BARS.items():
            with self.subTest(position=position):
                env = {}
                page = MagicMock()
                with patch.object(Application, 'IS_HTTP', True), \
                     patch.object(Application, 'get_request_method', return_value='GET'), \
                     patch.object(Application, 'storage', return_value=env), \
                     patch.object(module_counter, 'get_config_val', return_value=position), \
                     patch.object(module_counter, 'count_up') as increment, \
                     patch('gdo.counter.Counter.Counter') as counter, \
                     patch('gdo.counter.module_counter.t', return_value='Pagecount: 42'):
                    counter.return_value.get.return_value = 42
                    module = module_counter()
                    module.on_user_request(None)
                    module.gdo_init_sidebar(page)
                    module.on_response_headers()
                    increment.assert_called_once_with('pagecount')
                    field = getattr(page, bar).add_field.call_args.args[0]
                    self.assertEqual('Pagecount: 42', field.render_html())

    def test_pagecount_translation_and_fallback(self):
        lang_dir = Path(__file__).resolve().parents[1] / 'lang'
        translations = {}
        for iso in ('en', 'de'):
            with (lang_dir / f'counter_{iso}.toml').open('rb') as source:
                translations[iso] = tomllib.load(source)
        with patch.object(Trans, 'EN', translations['en']), \
             patch.object(Trans, 'CACHE', translations):
            self.assertEqual('Pagecount: 42', Trans.tiso2('en', 'counter_pagecount_display', (42,)))
            self.assertEqual('Seitenaufrufe: 42', Trans.tiso2('de', 'counter_pagecount_display', (42,)))
            self.assertEqual('Pagecount: 42', Trans.tiso2('sv', 'counter_pagecount_display', (42,)))

    def test_disabled_and_post_do_not_increment(self):
        for position, method in ((None, 'GET'), ('left', 'POST')):
            with self.subTest(position=position, method=method):
                with patch.object(Application, 'IS_HTTP', True), \
                     patch.object(Application, 'get_request_method', return_value=method), \
                     patch.object(Application, 'storage', return_value={}), \
                     patch.object(module_counter, 'get_config_val', return_value=position), \
                     patch.object(module_counter, 'count_up') as increment:
                    module_counter().on_response_headers()
                    increment.assert_not_called()

    def test_non_html_get_and_new_requests_count(self):
        with patch.object(Application, 'IS_HTTP', True), \
             patch.object(Application, 'get_request_method', return_value='GET'), \
             patch.object(Application, 'storage', side_effect=[{}, {}]), \
             patch.object(module_counter, 'get_config_val', return_value='bottom'), \
             patch.object(module_counter, 'count_up') as increment:
            module = module_counter()
            module.on_response_headers()
            module.on_response_headers()
            self.assertEqual(2, increment.call_count)

    def test_failed_increment_is_not_retried(self):
        env = {}
        with patch.object(Application, 'IS_HTTP', True), \
             patch.object(Application, 'get_request_method', return_value='GET'), \
             patch.object(Application, 'storage', return_value=env), \
             patch.object(module_counter, 'get_config_val', return_value='left'), \
             patch.object(module_counter, 'count_up', side_effect=OSError('disk')) as increment, \
             patch('gdo.counter.module_counter.Logger.exception'):
            module = module_counter()
            module.on_response_headers()
            module.on_response_headers()
            increment.assert_called_once()
