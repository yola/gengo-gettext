#!/usr/bin/env python
"""Gengo gettext."""

import polib
import os
import sys
from gengo import Gengo

from yoconfigurator.base import read_config

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
config = read_config(PROJECT_ROOT)

gengo = Gengo(
    public_key=str(config.gengo.public_key),
    private_key=str(config.gengo.private_key),
    sandbox=True,
)
submitted_strings = {
    'pl': [],
}
new_jobs = []


def po_file(lang, domain):
    """Return po path."""
    localedir = os.path.join(PROJECT_ROOT, 'locale')
    return os.path.join(localedir, lang, 'LC_MESSAGES', '%s.po' % domain)


def create_job(lang, text):
    """Create new gengo translation job.

    Must take care, gengo allows duplicate submissions and charges for each.

    Dev documentation:
    http://developers.gengo.com/client_libraries/

    """
    if text in submitted_strings[lang]:
        return
    sys.stdout.write('.')
    job = {
        'body_src': text,
        'lc_src': 'en',
        'lc_tgt': lang,
        'tier': 'standard',
    }
    new_jobs.append(job)


def create_jobs():
    """TODO cycle langs."""
    po = polib.pofile(po_file('pl', 'django'))
    sys.stdout.write("Creating Jobs...")
    for entry in po:
        if not entry.msgstr:
            create_job('pl', entry.msgid)


def post_jobs():
    """Post job, fails if too expensive."""
    print "\nPosting Jobs..."
    response = gengo.postTranslationJobs(jobs=new_jobs)
    print response


def get_submitted_strings():
    """TODO."""
    # get all job ids: getTranslationJobs(count=200)
    # going to run into issue with max count
    # get all job details: gengo.getTranslationJobBatch(id="1,2,..200")
    pass


if __name__ == '__main__':
    get_submitted_strings()
    create_jobs()
    post_jobs()
