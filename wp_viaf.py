#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
import sys
import sqlalchemy
import time
import sqlite3
from simplemediawiki import MediaWiki

from mbbot.utils.pidfile import PIDFile
from editing import MusicBrainzClient
from utils import extract_page_title
import config as cfg


engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

sdb = sqlite3.connect('wp_viaf.db')
sdb.executescript("""
CREATE TABLE IF NOT EXISTS pages_with_viaf (
    pageid INTEGER PRIMARY KEY,
    title
);
CREATE TABLE IF NOT EXISTS pages_with_viaf_eicontinue (eicontinue);
CREATE TABLE IF NOT EXISTS viaf (
    artist PRIMARY KEY,
    url,
    viaf
);
""")

wp_lang = sys.argv[1] if len(sys.argv) > 1 else 'en'
wp = MediaWiki('http://%s.wikipedia.org/w/api.php' % wp_lang)

#mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)


wp_url_query = """
SELECT DISTINCT a.id, a.gid, an.name, u.url
FROM artist a
JOIN artist_name an ON a.name = an.id
JOIN l_artist_url l ON l.entity0 = a.id AND l.link IN (SELECT id FROM link WHERE link_type = 179)
JOIN url u ON u.id = l.entity1
WHERE
    l.edits_pending = 0 AND
    u.url LIKE 'http://"""+wp_lang+""".wikipedia.org/wiki/%%'
ORDER BY a.id
"""


def fetch_pages_with_viaf():
    last_pageid = None
    rows = sdb.execute("SELECT pageid, title FROM pages_with_viaf ORDER BY pageid")
    for pageid, title in rows:
        last_pageid = pageid
        yield title

    return

    query = {
        'action': 'query',
        'list': 'embeddedin',
        'eititle': 'Template:Authority_control/VIAF',
        'eilimit': 500,
    }

    row = sdb.execute('SELECT eicontinue FROM pages_with_viaf_eicontinue').fetchone()
    if row is not None:
        query['eicontinue'] = row[0]

    has_more = True
    while has_more:
        print "calling Wikipedia API", query
        result = wp.call(query)
        for page in result['query']['embeddedin']:
            if page['pageid'] > last_pageid:
                last_pageid = page['pageid']
                sdb.execute('INSERT INTO pages_with_viaf (pageid, title) VALUES (?, ?)', (page['pageid'], page['title']))
                yield page['title']
        sdb.execute('DELETE FROM pages_with_viaf_eicontinue')
        if 'query-continue' in result:
            query['eicontinue'] = result['query-continue']['embeddedin']['eicontinue']
            sdb.execute('INSERT INTO pages_with_viaf_eicontinue (eicontinue) VALUES (?)', (query['eicontinue'], ))
        else:
            has_more = False
        sdb.commit()
        time.sleep(1.0)


def fetch_viaf(page):
    query = {
        'action': 'query',
        'titles': page,
        'prop': 'revisions',
        'rvprop': 'content'
    }
    result = wp.call(query)

    normalized_titles = {}
    if 'normalized' in result:
        for n in result['query']['normalized']:
            normalized_titles[n['from']] = n['to']

    for p in result['query']['pages'].itervalues():
        if p['title'] == normalized_titles.get(page, page):
            m = re.search(r'{{Authority[_ ]control\s*\|([^}]+?)}}', p['revisions'][0]['*'])
            if m is None:
                print p
                raise Exception
            for pair in m.group(1).split('|'):
                name, value = pair.replace(' ', '').split('=', 2)
                if name == 'VIAF':
                    return 'http://viaf.org/viaf/%d/' % (int(value), )


def main():
    pages_with_viaf = set()
    for page in fetch_pages_with_viaf():
        pages_with_viaf.add(page)

    artist_viaf = {}
    rows = sdb.execute("SELECT artist, url, viaf FROM viaf")
    for artist, url, viaf in rows:
        artist_viaf[artist] = {'url': url, 'viaf': viaf, 'submitted': submitted}

    cnt = 0
    for artist in db.execute(wp_url_query):
        if artist['id'] in artist_viaf:
            continue
        page = extract_page_title(artist['url'], wp_lang, normalize=True)
        if page not in pages_with_viaf:
            continue
        cnt += 1
        viaf = fetch_viaf(page)
        print artist, viaf
        sdb.execute('INSERT INTO viaf (artist, url, viaf) VALUES (?, ?, ?)', (artist['id'], artist['url'], viaf))
        sdb.commit()
    print cnt


if __name__ == '__main__':
    with PIDFile('/tmp/mbbot_wp_viaf.pid'):
        main()

