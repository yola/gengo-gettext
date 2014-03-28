#!/usr/bin/env python
"""Gengo gettext."""

import argparse
import json
import os
import sys

from gengo import Gengo
import polib
from yoconfigurator.base import read_config

import cache


DEBUG = False
PROJECT_ROOT = os.path.dirname(os.path.realpath(__file__))
config = read_config(PROJECT_ROOT)['gengo-gettext']

gengo = Gengo(
    public_key=str(config.gengo.public_key),
    private_key=str(config.gengo.private_key),
    sandbox=True,
)


def po_file(locale_dir, lang, domain):
    """Return po path."""
    return os.path.join(locale_dir, lang, 'LC_MESSAGES', '%s.po' % domain)


def create_job(lang, text):
    """Create new gengo translation job.

    Must take care, gengo allows duplicate submissions and charges for each.

    Dev documentation:
    http://developers.gengo.com/client_libraries/

    """
    if cache.Job.find(text, lang):
        if DEBUG:
            print "Skipping..."
        return

    job = {
        'body_src': text,
        'lc_src': 'en',
        'lc_tgt': lang,
        'tier': 'standard',
    }
    return job


def create_jobs(locale_dir, langs, domain):
    """Walk through all the langs in a text domain and return jobs"""
    for lang in langs:
        filename = po_file(locale_dir, lang, domain)
        if DEBUG:
            print "Processing %s" % filename
        if not os.path.exists(filename):
            print "Missing PO file: %s" % filename
            continue
        po = polib.pofile(filename)
        sys.stdout.write("Creating Jobs...")
        sys.stdout.flush()
        for entry in po:
            if not entry.msgstr:
                job = create_job(lang, entry.msgid)
                if job:
                    yield job
                sys.stdout.write('.')
                sys.stdout.flush()

        sys.stdout.write("\n")
        sys.stdout.flush()

    # TODO: Wait until all jobs have appeared in the API, or we could
    # accidentally re-submit them.


def post_jobs(jobs):
    """Post job, fails if too expensive."""
    print "Posting Jobs..."
    response = gengo.postTranslationJobs(jobs=jobs)
    print response


def get_submitted_strings():
    """TODO."""
    # get all job ids: getTranslationJobs(count=200)
    # going to run into issue with max count
    # get all job details: gengo.getTranslationJobBatch(id="1,2,..200")
    pass


def update_db():
    latest_order = cache.latest_order()
    if not latest_order:
        r = gengo.getTranslationJobs(count=200)
    else:
        r = gengo.getTranslationJobs(count=200,
                                     timestamp_after=latest_order.created)

    job_ids = [job['job_id'] for job in r['response']]
    r = gengo.getTranslationJobBatch(id=','.join(job for job in job_ids))

    orders = {}
    if r['response']:
        for job_data in r['response']['jobs']:
            job = cache.Job(id=job_data['job_id'],
                            order_id=job_data['order_id'],
                            string=job_data['body_src'],
                            language=job_data['lc_tgt'],
                            status=job_data['status'],
                           )
            job.save()
            orders[job_data['order_id']] = job_data['ctime']

        for order_id, ctime in orders.iteritems():
            order = cache.Order(id=order_id, created=ctime)
            order.save()

    # TODO update statuses


def main():
    global DEBUG
    p = argparse.ArgumentParser()
    p.add_argument('-b', '--basedir',
                   help='Base directory (containing language sub-directories)')
    p.add_argument('-l', '--langugage', action='append', dest='languages',
                   help='Language to translate to. '
                        'Can be specified multiple times')
    p.add_argument('-d', '--domain', default='messages',
                   help='Gettext domain (default: messages)')
    p.add_argument('-v', '--verbose', action='store_true',
                   help='Display debugging messages')
    args = p.parse_args()

    DEBUG = args.verbose

    update_db()

    jobs = create_jobs(args.basedir, args.languages, args.domain)
    if DEBUG:
        jobs = list(jobs)
        print json.dumps(jobs, indent=2)
    if jobs:
        post_jobs(jobs)

if __name__ == '__main__':
    main()
