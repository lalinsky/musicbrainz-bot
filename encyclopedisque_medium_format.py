#!/usr/bin/python

import re
import sqlalchemy
import solr
from editing import MusicBrainzClient
import pprint
import urllib
import time
from utils import mangle_name, join_names, out, colored_out, bcolors
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

"""
CREATE TABLE bot_encyclopedisque_medium_format (
    gid uuid NOT NULL,
    processed timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY bot_encyclopedisque_medium_format
    ADD CONSTRAINT bot_encyclopedisque_medium_format_pkey PRIMARY KEY (gid);

"""

query = """
WITH
    releases_wo_7inch AS (
        SELECT r.id, u.url, m.format
        FROM release r
            JOIN medium m ON m.release = r.id
            JOIN l_release_url l ON l.entity0 = r.id AND l.link IN (SELECT id FROM link WHERE link_type = 78)
            JOIN url u ON u.id = l.entity1
        WHERE u.url LIKE 'http://www.encyclopedisque.fr/images/%%'
            AND (m.format IS NULL OR m.format = 7)
            AND NOT EXISTS (SELECT 1 FROM l_release_url WHERE l_release_url.entity1 = u.id AND l_release_url.entity0 <> r.id)
    )
SELECT r.id, r.gid, r.name, ta.url, ta.format, ac.name
FROM releases_wo_7inch ta
JOIN s_release r ON ta.id = r.id
JOIN s_artist_credit ac ON r.artist_credit=ac.id
LEFT JOIN bot_encyclopedisque_medium_format b ON r.gid = b.gid
WHERE b.gid IS NULL
ORDER BY r.artist_credit, r.id
LIMIT 100
"""

for id, gid, name, url, format, ac_name in db.execute(query):
    colored_out(bcolors.OKBLUE, 'Looking up release "%s" by "%s" http://musicbrainz.org/release/%s' % (name, ac_name, gid))

    edit_note = 'Setting format to 7" based on attached link to Encyclopedisque (%s)' % url
    out(' * edit note: %s' % (edit_note,))
    mb.set_release_medium_format(gid, format, 29, edit_note)

    time.sleep(5)

    db.execute("INSERT INTO bot_encyclopedisque_medium_format (gid) VALUES (%s)", (gid,))
