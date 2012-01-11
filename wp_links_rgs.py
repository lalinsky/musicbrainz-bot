import re
import sqlalchemy
import solr
from simplemediawiki import MediaWiki
from editing import MusicBrainzClient
import pprint
import urllib
import time
from utils import mangle_name, join_names, out, get_page_content, extract_page_title
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

wp = MediaWiki('http://en.wikipedia.org/w/api.php')
wps = solr.SolrConnection('http://localhost:8983/solr/wikipedia')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

"""
CREATE TABLE bot_wp_rg (
    gid uuid NOT NULL,
    processed timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY bot_wp_rg
    ADD CONSTRAINT bot_wp_rg_pkey PRIMARY KEY (gid);
"""

query = """
WITH
    rgs_wo_wikipedia AS (
        SELECT a.id
        FROM release_group a
        LEFT JOIN l_release_group_url l ON
            l.entity0 = a.id AND
            l.link IN (SELECT id FROM link WHERE link_type = 89)
        WHERE a.artist_credit > 2 AND l.id IS NULL AND (a.type IS NULL OR a.type IN (SELECT id FROM release_group_type WHERE name IN ('Album', 'EP', 'Live', 'Remix', 'Compilation')))
        ORDER BY a.artist_credit, a.id
        LIMIT 100000
    )
SELECT a.id, a.gid, a.name, ac.name
FROM rgs_wo_wikipedia ta
JOIN s_release_group a ON ta.id=a.id
JOIN s_artist_credit ac ON a.artist_credit=ac.id
LEFT JOIN bot_wp_rg b ON a.gid = b.gid
WHERE b.gid IS NULL
ORDER BY a.artist_credit, a.id
LIMIT 1000
"""

query_album_tracks = """
SELECT DISTINCT t.name
FROM s_track t
JOIN tracklist tl ON t.tracklist=tl.id
JOIN medium m ON tl.id=m.tracklist
JOIN release r ON m.release=r.id
WHERE r.release_group = %s
"""
category_re = re.compile(r'\[\[Category:(.+?)(?:\|.*?)?\]\]')

def escape_query(s):
    s = re.sub(r'\bOR\b', 'or', s)
    s = re.sub(r'\bAND\b', 'and', s)
    s = re.sub(r'\+', '\\+', s)
    return s

for rg_id, rg_gid, rg_name, ac_name in db.execute(query):
    out('Looking up release group "%s" http://musicbrainz.org/release-group/%s' % (rg_name, rg_gid))
    matches = wps.query(escape_query(rg_name), defType='dismax', qf='name', rows=100).results
    last_wp_request = time.time()
    for match in matches:
        title = match['name']
        if mangle_name(re.sub(' \(.+\)$', '', title)) != mangle_name(rg_name) and mangle_name(title) != mangle_name(rg_name):
            continue
        delay = time.time() - last_wp_request
        if delay < 1.0:
            time.sleep(1.0 - delay)
        last_wp_request = time.time()
        page_orig = get_page_content(wp, title)
        if not page_orig:
            continue
        page_title = title
        url = 'http://en.wikipedia.org/wiki/%s' % (urllib.quote(page_title.encode('utf8').replace(' ', '_')),)
        out(' * trying article %s' % (url,))
        page = mangle_name(page_orig)
        if 'redirect' in page:
            out(' * redirect page, skipping')
            continue
        if 'disambiguation' in title:
            out(' * disambiguation page, skipping')
            continue
        if '{{disambig' in page_orig.lower():
            out(' * disambiguation page, skipping')
            continue
        if 'disambiguationpages' in page:
            out(' * disambiguation page, skipping')
            continue
        categories = category_re.findall(page_orig)
        is_album_page = False
        for category in categories:
            if category.lower().endswith(' albums'):
                is_album_page = True
                break
            #if category.lower().endswith(' singles'):
            #    is_album_page = True
            #    break
            if category.lower().endswith(' soundtracks'):
                is_album_page = True
                break
        if not is_album_page:
            out(' * not an album page, skipping')
            continue
        if mangle_name(ac_name) not in page:
            out(' * artist name not found')
            continue
        found_tracks = []
        tracks = set([r[0] for r in db.execute(query_album_tracks, (rg_id,))])
        tracks_to_ignore = set()
        for track in tracks:
            mangled_track = mangle_name(track)
            if len(mangled_track) <= 4 or mangle_name(rg_name) in mangle_name(track):
                tracks_to_ignore.add(track)
        tracks -= tracks_to_ignore
        if len(tracks) < 5:
            continue
        for track in tracks:
            mangled_track = mangle_name(track)
            if len(mangled_track) > 4 and mangled_track in page:
                found_tracks.append(track)
            else:
                out(" * track %s not found" % (track,))
        ratio = len(found_tracks) * 1.0 / len(tracks)
        out(' * ratio: %s, has tracks: %s, found tracks: %s' % (ratio, len(tracks), len(found_tracks)))
        min_ratio = 0.7 if len(rg_name) > 4 else 1.0
        if ratio < min_ratio:
            continue
        auto = ratio > 0.75
        text = 'Matched based on the name. The page mentions artist "%s" and %s.' % (ac_name, join_names('track', found_tracks),)
        out(' * linking to %s' % (url,))
        out(' * edit note: %s' % (text,))
        time.sleep(5)
        mb.add_url("release_group", rg_gid, 89, url, text, auto=auto)
        break
    db.execute("INSERT INTO bot_wp_rg (gid) VALUES (%s)", (rg_gid,))

