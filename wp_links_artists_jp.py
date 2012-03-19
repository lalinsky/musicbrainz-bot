# -*- coding: utf8 -*-

import re
import sqlalchemy
import solr
from simplemediawiki import MediaWiki
from editing import MusicBrainzClient
import pprint
import urllib
import time
from utils import mangle_name, join_names, contains_text_in_script, quote_page_title
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

wp = MediaWiki('http://ja.wikipedia.org/w/api.php')
wps = solr.SolrConnection('http://localhost:8983/solr/wikipedia_ja')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

"""
CREATE TABLE bot_wp_artist_ja (
    gid uuid NOT NULL,
    processed timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY bot_wp_artist_ja
    ADD CONSTRAINT bot_wp_artist_jpkey PRIMARY KEY (gid);
"""

query = """
WITH
    artists_wo_wikipedia AS (
        SELECT a.id
        FROM artist a
        LEFT JOIN l_artist_url l ON
            l.entity0 = a.id AND
            l.link IN (SELECT id FROM link WHERE link_type = 179)
        WHERE a.id > 2 AND l.id IS NULL
    ),
    artists_with_jp_releases AS (
        SELECT DISTINCT acn.artist AS id
        FROM artist_credit_name acn
        JOIN release r ON acn.artist_credit = r.artist_credit
        JOIN country c ON r.country = c.id
        WHERE c.iso_code = 'JP'
    )
SELECT a.id, a.gid, a.name
FROM artists_wo_wikipedia ta
JOIN s_artist a ON ta.id=a.id
JOIN artists_with_jp_releases jp_a ON jp_a.id=a.id
LEFT JOIN bot_wp_artist_ja b ON a.gid = b.gid
WHERE b.gid IS NULL
ORDER BY a.id
LIMIT 10000
"""

query_artist_albums = """
SELECT rg.name
FROM s_release_group rg
JOIN artist_credit_name acn ON rg.artist_credit = acn.artist_credit
WHERE acn.artist = %s
UNION
SELECT r.name
FROM s_release r
JOIN artist_credit_name acn ON r.artist_credit = acn.artist_credit
WHERE acn.artist = %s
"""

processed = 0
skipped = 0
for id, gid, name in db.execute(query):
    processed += 1
    if not contains_text_in_script(name, ['Katakana', 'Hiragana', 'Han']):
        skipped += 1
        db.execute("INSERT INTO bot_wp_artist_ja (gid) VALUES (%s)", (gid,))
        continue
    print 'Looking up artist "%s" http://musicbrainz.org/artist/%s' % (name, gid)
    matches = wps.query(name, defType='dismax', qf='name', rows=50).results
    last_wp_request = time.time()
    for match in matches:
        title = match['name']
        if title.endswith('album)') or title.endswith('song)'):
            continue
        if mangle_name(re.sub(' \(.+\)$', '', title)) != mangle_name(name) and mangle_name(title) != mangle_name(name):
            continue
        delay = time.time() - last_wp_request
        if delay < 1.0:
            time.sleep(1.0 - delay)
        last_wp_request = time.time()
        resp = wp.call({'action': 'query', 'prop': 'revisions', 'titles': title, 'rvprop': 'content'})
        pages = resp['query']['pages'].values()
        if not pages or 'revisions' not in pages[0]:
            continue
        page = mangle_name(pages[0]['revisions'][0].values()[0])
        if u'曖昧さ回避' in page:
            print ' * disambiguation, skipping'
            continue
        print ' * trying article "%s"' % (title,)
        page_title = pages[0]['title']
        found_albums = []
        albums = set([r[0] for r in db.execute(query_artist_albums, (id, id))])
        albums_to_ignore = set()
        for album in albums:
            if mangle_name(name) in mangle_name(album):
                albums_to_ignore.add(album)
        albums -= albums_to_ignore
        if not albums:
            continue
        for album in albums:
            mangled_album = mangle_name(album)
            if len(mangled_album) > 4 and mangled_album in page:
                found_albums.append(album)
        ratio = len(found_albums) * 1.0 / len(albums)
        print ' * ratio: %s, has albums: %s, found albums: %s' % (ratio, len(albums), len(found_albums))
        min_ratio = 0.2
        if len(found_albums) < 2:
            continue
        if ratio < min_ratio:
            continue
        url = 'http://ja.wikipedia.org/wiki/%s' % (quote_page_title(page_title),)
        text = 'Matched based on the name. The page mentions %s.' % (join_names('album', found_albums),)
        print ' * linking to %s' % (url,)
        print ' * edit note: %s' % (text,)
        mb.add_url("artist", gid, 179, url, text)
        break
    db.execute("INSERT INTO bot_wp_artist_ja (gid) VALUES (%s)", (gid,))

print processed, skipped
