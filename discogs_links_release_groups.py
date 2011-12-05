# -*- coding: utf-8 -*-
import re
import random
import locale
from collections import defaultdict
import itertools
import sqlalchemy
import discogs_client as discogs
from editing import MusicBrainzClient
import Levenshtein
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute('SET search_path TO musicbrainz')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

discogs.user_agent = 'MusicBrainzDiscogsReleaseGroupsBot/0.1 +https://github.com/weisslj/musicbrainz-bot'

query_rg_without_master = '''
SELECT rg.artist_credit, rg.id, rg.gid, release_name.name
FROM release_group rg
JOIN release_name ON rg.name = release_name.id
WHERE rg.id IN (
    SELECT DISTINCT rg.id
    FROM release_group rg
    JOIN release ON rg.id = release.release_group
    JOIN l_release_url l_ru ON release.id = l_ru.entity0
    JOIN link l ON l_ru.link = l.id
    WHERE l.link_type = 76
    
    EXCEPT
    
    SELECT rg.id
    FROM release_group rg
    JOIN l_release_group_url l_rgu ON rg.id = l_rgu.entity0
    JOIN link l ON l_rgu.link = l.id
    WHERE l.link_type = 90
)
'''

query_rg_release_discogs = '''
SELECT url.url
FROM l_release_url l_ru
JOIN link l ON l_ru.link = l.id
JOIN release ON release.id = l_ru.entity0
JOIN release_group rg ON rg.id = release.release_group
JOIN release_name ON release.name = release_name.id
JOIN url ON url.id = l_ru.entity1
WHERE release.release_group = %s AND l.link_type = 76
'''

def discogs_artists_str(artists):
    if len(artists) > 1:
        return ' and '.join([', '.join([a.name for a in artists[:-1]]), artists[-1].name])
    else:
        return artists[0].name

def discogs_get_master(release_urls):
    for release_url in release_urls:
        m = re.match(r'http://www.discogs.com/release/([0-9]+)', release_url)
        if m:
            release_id = int(m.group(1))
            release = discogs.Release(release_id)
            master = release.master
            if master:
                yield (master.title, master._id, discogs_artists_str(master.artists))

def out(t):
    print t.encode(locale.getpreferredencoding())

rg_by_ac = defaultdict(list)
for count, (ac, rg, gid, name) in enumerate(db.execute(query_rg_without_master)):
    rg_by_ac[ac].append((rg, gid, name))

rg_grouped = rg_by_ac.values()
random.shuffle(rg_grouped)

for i, (rg, gid, name) in enumerate(itertools.chain(*rg_grouped)):
    urls = set(u[0] for u in db.execute(query_rg_release_discogs, rg))
    if len(urls) < 2:
        continue
    out(u'%d/%d - %.2f%%' % (i, count, i * 100.0 / count))
    out(u'%s http://musicbrainz.org/release-group/%s' % (name, gid))
    masters = set(discogs_get_master(urls))
    if len(masters) > 1:
        out(u'  problematic release group')
        continue
    if len(masters) == 0:
        out(u'  no Discogs master!')
        continue
    master_name, master_id, master_artists = masters.pop()
    ratio = Levenshtein.ratio(master_name.lower(), name.lower())
    if ratio < 0.8:
        out(u'  Similarity ratio too small: %.2f' % ratio)
        continue
    master_url = 'http://www.discogs.com/master/%d' % master_id
    text = u'There are %d distinct Discogs links in this release group, and all point to this master URL.\n' % len(urls)
    text += u'The name of the Discogs master is “%s” (similarity: %.0f%%)' % (master_name, ratio * 100)
    text += u' by %s.' % master_artists
    out(u'  %s\n  %s' % (master_url, text))
    mb.add_url('release_group', gid, 90, master_url, text)
