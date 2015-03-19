# coding: utf-8
import collections
import contextlib
import errno
import os
import unittest

from mock import patch

import gengogettext


@contextlib.contextmanager
def ignoring(exception, errno=None):
    try:
        yield
    except exception as e:
        if errno and e.errno != errno:
            raise


class TestGengoGettext(unittest.TestCase):
    def setUp(self):
        self.db_name = 'tests.db'
        self.args = {
            'config': 'tests/projects.ini',
            'verbose': True,
            'database': self.db_name
        }
        with ignoring(OSError, errno.ENOENT):
            os.remove(self.db_name)

    def tearDown(self):
        with ignoring(OSError, errno.ENOENT):
            os.remove(self.db_name)

    @patch('requests.api.request')
    def test_only_updates_jobs(self, request):
        gengogettext.main(**self.args)
        self.assertTrue(request.call_count)
        called_url = request.call_args_list[1][0][1]
        self.assertIn('translate/jobs/', called_url)


class TestTranslationChecks(unittest.TestCase):

    def check_translation(self, source, translation):
        Job = collections.namedtuple('Job', ('source', 'translation'))
        job = Job(source, translation)
        return gengogettext.check_translation(job)

    def test_only_text(self):
        self.assertTrue(self.check_translation('Hello', 'Ciao'))

    def test_empty_translation(self):
        self.assertFalse(self.check_translation(
            'Hello',
            ' '))

    def test_correct_html(self):
        self.assertTrue(self.check_translation(
            'Click <a>this</a> link',
            'Ciicca <a>questo</a> link'))

    def test_missing_html(self):
        self.assertFalse(self.check_translation(
            'Click <a>this</a> link',
            'Ciicca <a>questo link'))

    def test_translated_html(self):
        self.assertFalse(self.check_translation(
            'Click <a>this</a> link',
            'Ciicca <un>questo</un> link'))

    def test_broken_html(self):
        self.assertFalse(self.check_translation(
            'Click <a class="blue">this</a> link',
            'Ciicca <a class=\'blue">questo</a> link'))

    def test_correct_substitution(self):
        self.assertTrue(self.check_translation(
            'Only $%s',
            'Solo $%s'))

    def test_missing_substitution(self):
        self.assertFalse(self.check_translation(
            'Only $%s',
            'Solo $s'))

    def test_correct_named_substitution(self):
        self.assertTrue(self.check_translation(
            'Only $%(price)s',
            'Solo $%(price)s'))

    def test_missing_named_substitution(self):
        self.assertFalse(self.check_translation(
            'Only $%(price)s',
            'Solo $s'))

    def test_translated_named_substitution(self):
        self.assertFalse(self.check_translation(
            'Only $%(price)s',
            'Solo $%(prezzo)s'))

    def test_missing_dollar_substitution(self):
        self.assertFalse(self.check_translation(
            'Only $%1$s',
            'Solo $%1s'))

    def test_unescaped_percent(self):
        self.assertFalse(self.check_translation(
            '2%% discount',
            'Sconto del 2%'))

    def test_correct_percent_escaping(self):
        self.assertFalse(self.check_translation(
            '2%% discount',
            'Sconto del 2%%'))

    def test_correct_entity(self):
        self.assertTrue(self.check_translation(
            'House &amp; Garden',
            'Casa &amp; Giardino'))

    def test_translated_entity(self):
        self.assertFalse(self.check_translation(
            'House &amp; Garden',
            'Casa &amplificatore; Giardino'))

    def test_spaced_entity(self):
        self.assertFalse(self.check_translation(
            'House &amp; Garden',
            'Casa & amp ; Giardino'))

    def test_full_width_semicolon_entity(self):
        self.assertFalse(self.check_translation(
            'House &amp; Garden',
            'Casa &amp； Giardino'))


class TestLanguageMangling(unittest.TestCase):
    def test_unmangled_locale_to_gengo(self):
        self.assertEqual(gengogettext.locale_to_gengo_language('it'),
                         ('it', None))

    def test_unmangled_gengo_to_locale(self):
        self.assertEqual(gengogettext.gengo_language_to_locale('it'), 'it')

    def test_mangle_bokmal_to_gengo(self):
        self.assertEqual(gengogettext.locale_to_gengo_language('nb'),
                         ('no', u'Norwegian Bokmål'))

    def test_mangle_bokmal_to_locale(self):
        self.assertEqual(gengogettext.gengo_language_to_locale('no'), 'nb')

    def test_mangle_chinese_to_gengo(self):
        self.assertEqual(gengogettext.locale_to_gengo_language('zh_CN'),
                         ('zh', u'Simplified Chinese'))

    def test_mangle_chinese_to_locale(self):
        self.assertEqual(gengogettext.gengo_language_to_locale('zh'), 'zh_CN')
