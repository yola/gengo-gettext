import os
import unittest

from mock import patch

import gengogettext


class TestGengoGettext(unittest.TestCase):

    def setUp(self):
        self.db_name = 'tests.db'
        self.args = {
            'config': 'tests/projects.ini',
            'verbose': True,
            'database': self.db_name
        }
        os.path.exists(self.db_name) and os.remove(self.db_name)

    def tearDown(self):
        if not os.path.exists(self.db_name):
            return
        os.remove(self.db_name)

    def test_runs_with_basic_args(self):
        gengogettext.main(**self.args)

    @patch('requests.api.request')
    def test_only_updates_jobs(self, request):
        gengogettext.main(**self.args)
        self.assertEqual(request.call_count, 1)
        called_url = request.call_args_list[0][0][1]
        self.assertIn('translate/jobs/', called_url)
