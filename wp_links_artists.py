#!/usr/bin/python

import sys
import re
import sqlalchemy
import solr
from simplemediawiki import MediaWiki
from editing import MusicBrainzClient
import pprint
import urllib
import time
from mbbot.wp.wikipage import WikiPage
from mbbot.wp.analysis import determine_country
from utils import mangle_name, join_names, out, colored_out, bcolors, escape_query
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

wp_lang = sys.argv[1] if len(sys.argv) > 1 else 'en'

wp = MediaWiki('http://%s.wikipedia.org/w/api.php' % wp_lang)

suffix = '_' + wp_lang if wp_lang != 'en' else ''
wps = solr.SolrConnection('http://localhost:8983/solr/wikipedia'+suffix)

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

"""

CREATE TABLE bot_wp_artist_link (
    gid uuid NOT NULL,
    lang character varying(2),
    processed timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY bot_wp_artist_link
    ADD CONSTRAINT bot_wp_artist_link_pkey PRIMARY KEY (gid, lang);

"""

acceptable_countries_for_lang = {
    'fr': ['FR', 'MC']
}
#acceptable_countries_for_lang['en'] = acceptable_countries_for_lang['fr']

query_params = []
no_country_filter = (wp_lang == 'en') and ('en' not in acceptable_countries_for_lang or len(acceptable_countries_for_lang['en']) == 0)
if no_country_filter:
    # Hack to avoid having an SQL error with an empty IN clause ()
    in_country_clause = 'TRUE'
else:
    placeHolders = ','.join( ['%s'] * len(acceptable_countries_for_lang[wp_lang]) )
    in_country_clause = "%s IN (%s)" % ('c.iso_code', placeHolders)
    query_params.extend(acceptable_countries_for_lang[wp_lang])
query_params.append(wp_lang)

query = """
WITH
    artists_wo_wikipedia AS (
        SELECT DISTINCT a.id, c.iso_code
        FROM artist a
        LEFT JOIN country c ON c.id = a.country
        LEFT JOIN (SELECT l.entity0 AS id
            FROM l_artist_url l
            JOIN url u ON l.entity1 = u.id AND u.url LIKE 'http://"""+wp_lang+""".wikipedia.org/wiki/%%'
            WHERE l.link IN (SELECT id FROM link WHERE link_type = 179)
        ) wpl ON wpl.id = a.id
        WHERE a.id > 2 AND wpl.id IS NULL
            AND (c.iso_code IS NULL OR """ + in_country_clause + """)
    )
SELECT a.id, a.gid, a.name, ta.iso_code AS country
FROM artists_wo_wikipedia ta
JOIN s_artist a ON ta.id=a.id
LEFT JOIN bot_wp_artist_link b ON a.gid = b.gid AND b.lang = %s
WHERE b.gid IS NULL
ORDER BY country NULLS LAST, a.id
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

for artist in db.execute(query, query_params):
    colored_out(bcolors.OKBLUE, 'Looking up artist "%s" http://musicbrainz.org/artist/%s' % (artist['name'], artist['gid']))
    matches = wps.query(escape_query(artist['name']), defType='dismax', qf='name', rows=50).results
    last_wp_request = time.time()
    for match in matches:
        title = match['name']
        if title.endswith('album)') or title.endswith('song)'):
            continue
        if mangle_name(re.sub(' \(.+\)$', '', title)) != mangle_name(artist['name']) and mangle_name(title) != mangle_name(artist['name']):
            continue
        delay = time.time() - last_wp_request
        if delay < 1.0:
            time.sleep(1.0 - delay)
        last_wp_request = time.time()
        wikipage = WikiPage.fetch('http://%s.wikipedia.org/wiki/%s' % (wp_lang, title))
        page_orig = wikipage.text
        if not page_orig:
            continue
        out(' * trying article "%s"' % (title,))
        page = mangle_name(page_orig)
        if 'redirect' in page:
            out(' * redirect page, skipping')
            continue
        if 'disambiguation' in title:
            out(' * disambiguation page, skipping')
            continue
        if '{{disambig' in page_orig.lower() or '{{disamb' in page_orig.lower():
            out(' * disambiguation page, skipping')
            continue
        if 'disambiguationpages' in page:
            out(' * disambiguation page, skipping')
            continue
        if 'homonymie' in page:
            out(' * disambiguation page, skipping')
            continue
        if 'infoboxalbum' in page:
            out(' * album page, skipping')
            continue
        page_title = title
        found_albums = []
        albums = set([r[0] for r in db.execute(query_artist_albums, (artist['id'], artist['id']))])
        albums_to_ignore = set()
        for album in albums:
            if mangle_name(artist['name']) in mangle_name(album):
                albums_to_ignore.add(album)
        albums -= albums_to_ignore
        if not albums:
            continue
        for album in albums:
            mangled_album = mangle_name(album)
            if len(mangled_album) > 6 and mangled_album in page:
                found_albums.append(album)
        ratio = len(found_albums) * 1.0 / len(albums)
        min_ratio = 0.15 if len(artist['name']) > 15 else 0.3
        colored_out(bcolors.WARNING if ratio < min_ratio else bcolors.NONE, ' * ratio: %s, has albums: %s, found albums: %s' % (ratio, len(albums), len(found_albums)))
        if ratio < min_ratio:
            continue

        # Check if wikipedia lang is compatible with artist country
        if wp_lang != 'en':
            if wp_lang not in acceptable_countries_for_lang:
                continue
            country, country_reasons = determine_country(wikipage)
            if (country not in acceptable_countries_for_lang[wp_lang] and artist['country'] not in acceptable_countries_for_lang[wp_lang]):
                colored_out(bcolors.HEADER, ' * artist country (%s) not compatible with wiki language (%s)' % (country, wp_lang))
                continue

        url = 'http://%s.wikipedia.org/wiki/%s' % (wp_lang, urllib.quote(page_title.encode('utf8').replace(' ', '_')),)
        text = 'Matched based on the name. The page mentions %s.' % (join_names('album', found_albums),)
        colored_out(bcolors.OKGREEN, ' * linking to %s' % (url,))
        out(' * edit note: %s' % (text,))
        time.sleep(60)
        mb.add_url("artist", artist['gid'], 179, url, text)
        break
    db.execute("INSERT INTO bot_wp_artist_link (gid, lang) VALUES (%s, %s)", (artist['gid'], wp_lang))

