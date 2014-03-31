#!/usr/bin/env python
"""Gengo gettext."""

import argparse
import json
import os
import sys
import time

from gengo import Gengo
import polib
from yoconfigurator.base import read_config

from orm import Job, Order


DEBUG = False
MAX_COST = 20

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


def check_entry(lang, entry):
    """
    Check a POEntry. Yield a job if one needs to be created.
    Update if there's a translation in our DB
    """
    # Translated
    if entry.msgstr and 'fuzzy' not in entry.flags:
        return

    # Translation in progress
    job = Job.find(lang, entry.msgid)
    if job:
        if job.status == 'approved':
            entry.msgstr = job.translation
            if 'fuzzy' in entry.flags:
                entry.flags.remove('fuzzy')
        if DEBUG:
            print 'Skipping...'
        return

    job = {
        'body_src': entry.msgid,
        'comment': "[Standard Yola Description]\n"
                   "Please leave <html> tags untranslated, but translate "
                   "words <em>between them</em>. "
                   "The 'html' and 'em' are left untranslated. "
                   "%s or %(string_id)s is a place were something will be "
                   "substituted. Don't translate 'string_id'. "
                   "\n[End of Standard Yola Description]",
        'lc_src': 'en',
        'lc_tgt': lang,
        'tier': 'standard',
        'purpose': 'Web localization',
    }
    if entry.msgstr:
        job['comment'] += ('\nFuzzy translation. Previous translation was:\n' +
                           entry.msgstr)
    return job


def walk_domain(locale_dir, langs, domain):
    """Walk through all the langs in a text domain and return jobs"""
    for lang in langs:
        filename = po_file(locale_dir, lang, domain)
        if DEBUG:
            print 'Processing %s' % filename
        if not os.path.exists(filename):
            print 'Missing PO file: %s' % filename
            continue
        po = polib.pofile(filename)
        print 'Creating jobs',
        sys.stdout.flush()
        for entry in po:
            job = check_entry(lang, entry)
            if job:
                yield job
            sys.stdout.write('.')
            sys.stdout.flush()
        po.save()
        print


def quote_jobs(jobs):
    job_dict = dict(enumerate(jobs))
    r = gengo.determineTranslationCost(jobs=job_dict)
    currency = None
    credits = 0
    for job in r['response']['jobs']:
        currency = job['currency']
        credits += job['credits']
    print 'Cost: %s %0.2f' % (currency, credits)
    return credits


def post_jobs(jobs):
    print 'Posting Jobs...'
    r = gengo.postTranslationJobs(jobs=jobs)
    order_id = r['response']['order_id']

    if DEBUG:
        print 'Waiting for the jobs to be available in the API...'
    while True:
        r = gengo.getTranslationOrderJobs(id=order_id)
        if int(r['response']['order']['jobs_queued']) == 0:
            break
        time.sleep(1)

    update_db()


def update_db():
    print 'Updating known orders...'
    latest_order = Order.get_latest()
    if not latest_order:
        r = gengo.getTranslationJobs(count=200)
    else:
        r = gengo.getTranslationJobs(timestamp_after=latest_order.created)

    job_ids = [job['job_id'] for job in r['response']]
    r = gengo.getTranslationJobBatch(id=','.join(job for job in job_ids))

    orders = {}
    if r['response']:
        for job_data in r['response']['jobs']:
            job = Job(
                id=job_data['job_id'],
                order_id=job_data['order_id'],
                lang=job_data['lc_tgt'],
                source=job_data['body_src'],
                translation=job_data.get('body_tgt', ''),
                status=job_data['status'],
            )
            job.save()
            orders[job_data['order_id']] = job_data['ctime']

        for order_id, ctime in orders.iteritems():
            order = Order(id=order_id, created=ctime)
            order.save()


def update_statuses():
    print 'Updating state of in-progress jobs...'
    jobs = {}
    for job in Job.get_in_progress():
        jobs[job.id] = job

    r = gengo.getTranslationJobBatch(id=','.join(str(id) for id in jobs))
    if r['response']:
        for job_data in r['response']['jobs']:
            job = jobs[int(job_data['job_id'])]
            job.status = job_data['status']
            job.translation = job_data.get('body_tgt', '')
            job.save()


def review():
    for job in Job.get_reviewable():
        print 'Review reviewable translation:'
        print 'en: %s' % job.source
        print '%s: %s' % (job.lang, job.translation)
        r = gengo.getTranslationJobComments(id=job.id)
        for comment in r['response']['thread']:
            comment['ctime_date'] = time.strftime(
                '%Y-%m-%d %H:%M:%S UTC', time.gmtime(comment['ctime']))
            print 'Comment: %(body)s  -- %(author)s %(ctime_date)s' % comment
        while True:
            action = raw_input('Action? [A]pprove, Approve with [C]omment, '
                               '[R]evise, [S]kip:')
            action = action.lower().strip()
            if action == 'a':
                gengo.updateTranslationJob(id=job.id,
                                           action={'action': 'approve'})
                break
            elif action == 'c':
                while True:
                    try:
                        rating = int(raw_input('Rating? (1-5):'))
                    except ValueError:
                        pass
                    if 1 <= rating <= 5:
                        break
                    else:
                        print 'Invalid rating'
                comment = raw_input('Comment: ')
                gengo.updateTranslationJob(id=job.id, action={
                    'action': 'approve',
                    'comment': comment,
                    'rating': rating,
                })
                break
            elif action == 'r':
                comment = raw_input('Comment: ')
                gengo.updateTranslationJob(id=job.id, action={
                    'action': 'revise',
                    'comment': comment,
                })
                break
            elif action == 's':
                break


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
    update_statuses()
    review()

    jobs = list(walk_domain(args.basedir, args.languages, args.domain))
    if DEBUG:
        print json.dumps(jobs, indent=2)
    if jobs:
        if quote_jobs(jobs) > MAX_COST:
            print "Too expensive, aborting"
            sys.exit(1)
        post_jobs(jobs)

if __name__ == '__main__':
    main()
