#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import os
import datetime
import re
import sqlalchemy
from editing import MusicBrainzClient
import pprint
import urllib
import time
from mbbot.utils.pidfile import PIDFile
from mbbot.wp.wikipage import WikiPage
from mbbot.wp.analysis import determine_country, determine_type, determine_gender, determine_begin_date, determine_end_date
from utils import mangle_name, join_names, mw_remove_markup, out, colored_out, bcolors, get_page_content, extract_page_title
import config as cfg

wp_lang = sys.argv[1] if len(sys.argv) > 1 else 'en'

CHECK_PERFORMANCE_NAME = False

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

"""
CREATE TABLE bot_wp_artist_data (
    gid uuid NOT NULL,
    lang character varying(2),
    processed timestamp with time zone DEFAULT now()
);

ALTER TABLE ONLY bot_wp_artist_data
    ADD CONSTRAINT bot_wp_artist_data_pkey PRIMARY KEY (gid, lang);

"""

query = """
SELECT DISTINCT
    a.id, a.gid, a.name, a.country, a.type, a.gender,
    a.begin_date_year,
    a.begin_date_month,
    a.begin_date_day,
    a.end_date_year,
    a.end_date_month,
    a.end_date_day,
    u.url
FROM s_artist a
JOIN l_artist_url l ON l.entity0 = a.id AND l.link IN (SELECT id FROM link WHERE link_type = 179)
JOIN url u ON u.id = l.entity1
LEFT JOIN bot_wp_artist_data b ON a.gid = b.gid
WHERE
    b.gid IS NULL AND
    (
        a.country IS NULL OR
        a.type IS NULL OR
        ((a.type IS NULL OR a.type = 1) AND (a.begin_date_year IS NULL OR a.gender IS NULL)) OR
        ((a.type IS NULL OR a.type = 2) AND (a.begin_date_year IS NULL))
    ) AND
    l.edits_pending = 0 AND
    u.url LIKE 'http://"""+wp_lang+""".wikipedia.org/wiki/%%'
ORDER BY a.id
LIMIT 50
"""

performance_name_query = """
SELECT count(*) FROM l_artist_artist
WHERE link IN (SELECT id FROM link WHERE link_type = 108)
AND entity1 = %s
"""

country_ids = {}
for id, code in db.execute("SELECT id, iso_code FROM country"):
    country_ids[code] = id

gender_ids = {}
for id, code in db.execute("SELECT id, lower(name) FROM gender"):
    gender_ids[code] = id

artist_type_ids = {}
for id, code in db.execute("SELECT id, lower(name) FROM artist_type"):
    artist_type_ids[code] = id

def main():
    seen = set()
    for artist in db.execute(query):
        if artist['id'] in seen:
            continue
        seen.add(artist['id'])
        colored_out(bcolors.OKBLUE, 'Looking up artist "%s" http://musicbrainz.org/artist/%s' % (artist['name'], artist['gid']))
        out(' * wiki:', artist['url'])

        artist = dict(artist)
        update = set()
        reasons = []

        page = WikiPage.fetch(artist['url'])

        if not artist['country']:
            country, country_reasons = determine_country(page)
            if country:
                country_id = country_ids[country]
                artist['country'] = country_id
                update.add('country')
                reasons.append(('COUNTRY', country_reasons))

        if not artist['type']:
            type, type_reasons = determine_type(page)
            if type:
                type_id = artist_type_ids[type]
                artist['type'] = type_id
                update.add('type')
                reasons.append(('TYPE', type_reasons))

        if not artist['gender'] and artist['type'] == 1:
            gender, gender_reasons = determine_gender(page)
            if gender:
                gender_id = gender_ids[gender]
                artist['gender'] = gender_id
                update.add('gender')
                reasons.append(('GENDER', gender_reasons))

        is_performance_name = False
        if artist['type'] == 1 and CHECK_PERFORMANCE_NAME:
            is_performance_name = db.execute(performance_name_query, artist['id']).scalar() > 0
            out(" * checking for performance name", is_performance_name)

        if not artist['begin_date_year']:
            begin_date, begin_date_reasons = determine_begin_date(artist, page, is_performance_name)
            if begin_date['year']:
                colored_out(bcolors.OKGREEN, " * new begin date:", begin_date)
                artist['begin_date_year'] = begin_date['year']
                artist['begin_date_month'] = begin_date['month']
                artist['begin_date_day'] = begin_date['day']
                update.add('begin_date')
                reasons.append(('BEGIN DATE', begin_date_reasons))
        if not artist['end_date_year']:
            end_date, end_date_reasons = determine_end_date(artist, page, is_performance_name)
            if end_date['year']:
                colored_out(bcolors.OKGREEN, " * new end date:", end_date)
                artist['end_date_year'] = end_date['year']
                artist['end_date_month'] = end_date['month']
                artist['end_date_day'] = end_date['day']
                update.add('end_date')
                reasons.append(('END DATE', end_date_reasons))

        if update:
            edit_note = 'From %s' % (artist['url'],)
            for field, reason in reasons:
                edit_note += '\n\n%s:\n%s' % (field, ' '.join(reason))
            out(' * edit note:', edit_note.replace('\n', ' '))
            time.sleep(10)
            mb.edit_artist(artist, update, edit_note)

        db.execute("INSERT INTO bot_wp_artist_data (gid, lang) VALUES (%s, %s)", (artist['gid'], wp_lang))
        out()

if __name__ == '__main__':
    with PIDFile('/tmp/mbbot_wp_artist_country.pid'):
        main()
