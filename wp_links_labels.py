import re
import sqlalchemy
import solr
from simplemediawiki import MediaWiki
from editing import MusicBrainzClient
import pprint
import urllib
import time
from utils import mangle_name, join_names
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

wp = MediaWiki('http://en.wikipedia.org/w/api.php')
wps = solr.SolrConnection('http://localhost:8983/solr/wikipedia')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

"""
CREATE TABLE bot_wp_label (
    gid uuid NOT NULL,
    processed timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY bot_wp_label
    ADD CONSTRAINT bot_wp_label_pkey PRIMARY KEY (gid);

"""

query = """
WITH
    labels_wo_wikipedia AS (
        SELECT a.id
        FROM label a
        LEFT JOIN l_label_url l ON
            l.entity0 = a.id AND
            l.link IN (SELECT id FROM link WHERE link_type = 216)
        WHERE a.id > 2 AND l.id IS NULL
    )
SELECT a.id, a.gid, a.name
FROM labels_wo_wikipedia ta
JOIN s_label a ON ta.id = a.id
LEFT JOIN bot_wp_label b ON a.gid = b.gid
WHERE b.gid IS NULL
ORDER BY a.id
LIMIT 10000
"""

query_label_artists = """
SELECT a.name
FROM s_artist a
JOIN artist_credit_name acn ON a.id = acn.artist
JOIN release r ON r.artist_credit = acn.artist_credit
JOIN release_label rl ON rl.release = r.id
WHERE rl.label = %s
"""

for id, gid, name in db.execute(query):
    print 'Looking up label "%s" http://musicbrainz.org/label/%s' % (name, gid)
    matches = wps.query(name.lower(), defType='dismax', qf='name', rows=50).results
    last_wp_request = time.time()
    for match in matches:
        page_title = match['name']
        if mangle_name(re.sub(' \(.+\)$', '', page_title)) != mangle_name(name) and mangle_name(page_title) != mangle_name(name):
            continue
        delay = time.time() - last_wp_request
        if delay < 1.0:
            time.sleep(1.0 - delay)
        last_wp_request = time.time()
        resp = wp.call({'action': 'query', 'prop': 'revisions', 'titles': page_title, 'rvprop': 'content'})
        pages = resp['query']['pages'].values()
        if not pages or 'revisions' not in pages[0]:
            continue
        page = mangle_name(pages[0]['revisions'][0].values()[0])
        if 'disambiguationpages' in page:
            print ' * disambiguation or album page, skipping'
            continue
        if 'recordlabels' not in page:
            print ' * not a record label page, skipping'
            continue
        page_title = pages[0]['title']
        print ' * trying article "%s"' % (page_title,)
        artists = set([r[0] for r in db.execute(query_label_artists, (id,))])
        if name in artists:
            artists.remove(name)
        if not artists:
            continue
        found_artists = []
        for artist in artists:
            mangled_artist = mangle_name(artist)
            if len(mangled_artist) > 5 and mangled_artist in page:
                found_artists.append(artist)
        ratio = len(found_artists) * 1.0 / len(artists)
        print ' * ratio: %s, has artists: %s, found artists: %s' % (ratio, len(artists), len(found_artists))
        if len(found_artists) < 2:
            continue
        url = 'http://en.wikipedia.org/wiki/%s' % (urllib.quote(page_title.encode('utf8').replace(' ', '_')),)
        text = 'Matched based on the name. The page mentions %s.' % (join_names('artist', found_artists),)
        print ' * linking to %s' % (url,)
        print ' * edit note: %s' % (text,)
        time.sleep(60)
        mb.add_url("label", gid, 216, url, text)
        break
    db.execute("INSERT INTO bot_wp_label (gid) VALUES (%s)", (gid,))

