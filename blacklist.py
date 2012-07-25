#!/usr/bin/env python
# -*- coding: utf-8 -*-
import urllib
import re
from HTMLParser import HTMLParser

from utils import extract_mbid

def discogs_links(entity):
    return wiki_get_rows('http://wiki.musicbrainz.org/Bots/Blacklist/Discogs_Links', entity)

def wiki_markup(bot_blacklist, entity, db):
    return u'\n'.join(u'|-\n| %s\n| %s\n| ' %
            (entity_col(e[0], entity, db), e[1]) for e in bot_blacklist)

def entity_col(gid, entity, db):
    if entity == 'artist':
        return generic_entity_col(gid, db, 'Artist', 'artist', 'artist_name')
    elif entity == 'label':
        return generic_entity_col(gid, db, 'Label', 'label', 'label_name')
    elif entity == 'release':
        return with_artist_entity_col(gid, db, 'Release', 'release', 'release_name')
    elif entity == 'release-group':
        return with_artist_entity_col(gid, db, 'ReleaseGroup', 'release_group', 'release_name')
    elif entity == 'recording':
        return with_artist_entity_col(gid, db, 'Recording', 'recording', 'track_name')
    elif entity == 'work':
        return generic_entity_col(gid, db, 'Work', 'work', 'work_name')
    else:
        return None

def generic_entity_col(gid, db, template, table, name_table):
    name, comment = entity_name(gid, db, table, name_table)
    col = u'[[%s:%s|%s]]' % (template, gid, name)
    if comment:
        col += u' (%s)' % comment
    return col

def with_artist_entity_col(gid, db, template, table, name_table):
    artist = entity_name(gid, db, 'artist', 'artist_name')[0]
    name, comment = entity_name(gid, db, table, name_table)
    col = u'[[%s:%s|%s]]' % (template, gid, u'%s – %s' % (artist, name))
    if comment:
        col += u' (%s)' % comment
    return col

def entity_name(gid, db, table, name_table):
    query = 'SELECT en.name, e.comment FROM '+table+' e JOIN '+name_table+' en ON e.name = en.id WHERE e.gid = %s'''
    return db.execute(query, gid).fetchone()

def wiki_get_rows(url, entity):
    f = urllib.urlopen(url)
    parser = LinkTableParser(entity)
    parser.feed(f.read())
    return parser.result()

class LinkTableParser(HTMLParser):
    def __init__(self, entity):
        HTMLParser.__init__(self)
        self.entity = entity
        self.trs = []
        self.tr = None
        self.td = None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr' and self.tr is None:
            self.tr = []
        if tag == 'td' and isinstance(self.tr, list) and self.td is None:
            self.td = []
        if tag == 'a' and isinstance(self.td, list):
            self.td.append(dict(attrs)['href'])
    def handle_endtag(self, tag):
        if tag == 'tr' and self.tr is not None:
            if len(self.tr) > 1:
                self.tr[0] = extract_mbid(self.tr[0], self.entity)
                if self.tr[0]:
                    self.trs.append(tuple(self.tr[:2]))
            self.tr = None
        if tag == 'td' and self.tr is not None and self.td is not None:
            if len(self.td) == 1:
                self.tr.append(self.td[0])
            self.td = None
    def result(self):
        return set(self.trs)
