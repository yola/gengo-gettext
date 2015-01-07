#!/usr/bin/env python
# coding: UTF-8
"""Gengo gettext."""

import argparse
import cgi
import ConfigParser
import itertools
import json
import os
import re
import sys
import time

from gengo import Gengo, GengoError
import polib
from yoconfigurator.base import read_config

import orm
from orm import Job, Order


DEBUG = False
MAX_COST = 100
COMMENT = ''
_gengo = None


def gengo():
    global _gengo
    if not _gengo:
        PROJECT_ROOT = os.path.dirname(os.path.realpath(__file__))
        config = read_config(PROJECT_ROOT)['gengo-gettext']
        _gengo = Gengo(
            public_key=str(config.gengo.public_key),
            private_key=str(config.gengo.private_key),
            sandbox=config.gengo.sandbox,
        )
    return _gengo


def po_file(locale_dir, lang, domain):
    """Return po path."""
    return os.path.join(locale_dir, lang, 'LC_MESSAGES', '%s.po' % domain)


def check_entry(lang, entry):
    """
    Check a POEntry. Return a job if one needs to be created.
    Update if there's a translation in our DB
    """
    # Translated
    if entry.msgstr and 'fuzzy' not in entry.flags:
        return 'ok', None

    # Translation in progress
    job = Job.find(lang, entry.msgid)
    if job:
        if DEBUG:
            print 'Skipping...'
        if job.status == 'approved':
            entry.msgstr = job.translation
            if 'fuzzy' in entry.flags:
                entry.flags.remove('fuzzy')
            return 'updated', None
        return 'waiting', None

    job = {
        'body_src': entry.msgid,
        'comment': COMMENT,
        'lc_src': 'en',
        'lc_tgt': lang,
        'tier': 'standard',
        'purpose': 'Web localization',
    }
    if lang == 'nb':
        job['lc_tgt'] = 'no'
        job['comment'] += u'\nNorwegian Bokmål'
    if entry.msgstr:
        job['comment'] += ('\nFuzzy translation. Previous translation was:\n' +
                           entry.msgstr)
    return 'job', job


def walk_po_file(locale_dir, lang, domain):
    """Walk through a po file and yield any jobs that need to be submitted"""
    filename = po_file(locale_dir, lang, domain)
    if DEBUG:
        print 'Processing %s' % filename
    if not os.path.exists(filename):
        print 'Missing PO file: %s' % filename
        return
    po = polib.pofile(filename)
    updated = False
    print 'Creating jobs',
    sys.stdout.flush()
    for entry in po:
        if entry.obsolete:
            continue
        action, job = check_entry(lang, entry)
        if job:
            yield job
        if action == 'updated':
            updated = True
        sys.stdout.write('.')
        sys.stdout.flush()
    if updated:
        po.save()
    print


def quote_jobs(jobs):
    job_dict = dict(enumerate(jobs))
    r = gengo().determineTranslationCost(jobs=job_dict)
    currency = None
    credits = 0
    for job in r['response']['jobs']:
        currency = job['currency']
        credits += job['credits']
    print 'Cost: %s %0.2f' % (currency, credits)
    return credits


def post_jobs(jobs):
    print 'Posting Jobs...'
    ctime = time.time()

    r = gengo().postTranslationJobs(jobs=jobs)
    order_id = r['response']['order_id']

    Order(id=order_id, created=ctime).save()

    if DEBUG:
        print 'Waiting for the jobs to be available in the API...'
    while True:
        r = gengo().getTranslationOrderJobs(id=order_id)
        if int(r['response']['order']['jobs_queued']) == 0:
            break
        time.sleep(1)

    for job in r['response']['order']['jobs_available']:
        Job(
            id=job,
            order_id=order_id,
            lang=None,
            source=None,
            translation=None,
            status='queued'
        ).save()

    update_statuses()


def update_db():
    print 'Updating known orders...'
    latest_order = Order.get_latest()
    if not latest_order:
        r = gengo().getTranslationJobs(count=200)
    else:
        # This is actually the latest 200 after N, which is a bit useless
        r = gengo().getTranslationJobs(timestamp_after=latest_order.created,
                                       count=200)

    job_ids = [job['job_id'] for job in r['response']]
    r = gengo().getTranslationJobBatch(id=','.join(job for job in job_ids))
    if not r['response']:
        return

    orders = {}
    for job_data in r['response']['jobs']:
        if Job.get_where('id = ?', (job_data['job_id'],)):
            continue
        lang = job_data['lc_tgt']
        if lang == 'no':
            lang = 'nb'
        job = Job(
            id=job_data['job_id'],
            order_id=job_data['order_id'],
            lang=lang,
            source=job_data['body_src'],
            translation=job_data.get('body_tgt', ''),
            status=job_data['status'],
        )
        job.save()
        orders[job_data['order_id']] = job_data['ctime']

    for order_id, ctime in orders.iteritems():
        order = Order(id=order_id, created=ctime)
        order.save()


def grouper(iterable, n, fillvalue=None):
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return itertools.izip_longest(fillvalue=fillvalue, *args)


def update_statuses():
    print 'Updating state of in-progress jobs...'
    for batch in grouper(Job.get_in_progress(), 100):
        jobs = {}
        for job in batch:
            if job:
                jobs[job.id] = job

        r = gengo().getTranslationJobBatch(id=','.join(str(id) for id in jobs))
        for job_data in r['response']['jobs']:
            job = jobs[int(job_data['job_id'])]
            job.status = job_data['status']
            job.source = job_data['body_src']
            job.translation = job_data.get('body_tgt', '')
            job.lang = job_data['lc_tgt']
            if job.lang == 'no':
                job.lang = 'nb'
            job.save()


def check_translation(job):
    passed = True

    if not job.translation.strip():
        print "Empty translation"
        passed = False

    # Check that some strings, if present in the source, are present,
    # identically, in the translation
    for regex, message in (
        (r'<.*?>', 'HTML tags'),
        (r'%(?:\([a-zA-Z0-9_]+\))[#0 +-]?(?:[0-9*]+\$?)?\.?(?:[0-9]+\$?)?'
         r'[diouxXeEfFgGcrs]',
         'Python interpolation'),
        (r'{[a-z0-9_]*(?:![rs])?'
         r'(?::(?:.?[<>=^])?[ +-]?#?0?[0-9]*,?(?:\.[0-9]+)?'
         r'[bcdeEfFgGnosxX%]?)?}', 'Python format string'),
        (r'%%', 'Escaped percent symbol'),
        (r'&[a-z]+;', 'HTML entity'),
    ):
        source_matches = set(re.findall(regex, job.source))
        translation_matches = set(re.findall(regex, job.translation))
        if source_matches != translation_matches:
            print "Differing %s" % message
            passed = False

    return passed


def fix_translation(job):
    # Auto-whitespace
    m = re.match(r'^(\s*).*?(\s*)$', job.source, re.DOTALL)
    translation = m.group(1) + job.translation.strip() + m.group(2)
    if translation != job.translation:
        job.translation = translation
        job.save()
        return True

    return False


def review():
    for job in list(Job.get_reviewable()):
        fix_translation(job)
        auto_checks = check_translation(job)

        if auto_checks:
            approve(job)
        else:
            manual_review(job)


def approve(job):
    try:
        gengo().updateTranslationJob(id=job.id,
                                     action={'action': 'approve'})
    except GengoError as e:
        print e


def revise(job):
    comment = raw_input('Comment: ')
    # Gengo's UI doesn't handle HTML in comments, correctly.
    comment = cgi.escape(comment)

    gengo().updateTranslationJob(id=job.id, action={
        'action': 'revise',
        'comment': comment,
    })


def manual_review(job):
    print '\nReview reviewable translation:', job.id
    print '===== en ====='
    print job.source
    print '===== %s =====' % job.lang
    print job.translation
    print '=============='
    r = gengo().getTranslationJobComments(id=job.id)
    for comment in r['response']['thread'][1:]:
        comment['ctime_date'] = time.strftime(
            '%Y-%m-%d %H:%M:%S UTC', time.gmtime(comment['ctime']))
        print 'Comment: %(body)s  -- %(author)s %(ctime_date)s' % comment

    while True:
        action = raw_input('Action? [A]pprove, [R]evise, S[k]ip: ')
        action = action.lower().strip()
        if action == 'a' or action == '':
            approve(job)
            break
        elif action == 'r':
            revise(job)
            break
        elif action == 'k':
            break


def main(**kwargs):
    global DEBUG, MAX_CONT, COMMENT, DB_NAME
    p = argparse.ArgumentParser()
    p.add_argument('-p', '--project', action='append', dest='projects',
                   help='Only look at the specified projects. '
                         'Can be repeated. Default: all')
    p.add_argument('-l', '--language', action='append', dest='languages',
                   help='Only look at the specified languages. '
                         'Can be repeated. Default: all')
    p.add_argument('-c', '--config', type=file, default='projects.ini',
                   help='Configuration file (default: projects.ini)')
    p.add_argument('-v', '--verbose', action='store_true',
                   help='Display debugging messages')
    p.add_argument('-d', '--database', default='jobs.db',
                   help='Local jobs database (default: jobs.db)')
    p.set_defaults(**kwargs)
    args = p.parse_args()

    config = ConfigParser.SafeConfigParser()
    config.readfp(args.config)

    DEBUG = args.verbose
    orm.DB_NAME = args.database

    projects = args.projects or config.sections()
    if 'GLOBAL' in projects:
        projects.remove('GLOBAL')

    COMMENT = config.get('GLOBAL', 'comment')
    MAX_COST = config.getint('GLOBAL', 'max_cost')

    update_db()
    update_statuses()
    review()

    jobs = []
    for project in projects:
        languages = args.languages or config.get(project, 'languages').split()
        for domain in config.get(project, 'domains').split():
            basedir = config.get(project, domain)
            for language in languages:
                jobs.extend(walk_po_file(basedir, language, domain))

    if DEBUG:
        print json.dumps(jobs, indent=2)
    if jobs:
        if quote_jobs(jobs) > MAX_COST:
            print "Too expensive, aborting"
            sys.exit(1)
        post_jobs(jobs)


if __name__ == '__main__':
    main()
