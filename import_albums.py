import re
import sys
import urllib
import urllib2
import config
import pymongo
import pprint
from editing import MusicBrainzClient
import cgi


mb = MusicBrainzClient('lukz_bot', 'mb', 'http://mb.muziq.eu')


opener = urllib2.build_opener()
if config.WWW_USER_AGENT:
    opener.addheaders = [('User-Agent', config.WWW_USER_AGENT)]


mongo = pymongo.Connection()
db = mongo.mbot


html_escape_table = {
    "&": "&amp;",
    '"': "&quot;",
    "'": "&apos;",
    ">": "&gt;",
    "<": "&lt;",
    }

def html_escape(text):
    """Produce entities within text."""
    return "".join(html_escape_table.get(c,c) for c in text)


for album in db.albums.find({'status': {'imported': False}})[:1]:
    artist_key = 'cdbaby:' + album['artist_cdbaby_id']
    if 'type' not in album:
        album['type'] = 'album'
    album_url = 'http://www.cdbaby.com/cd/' + album['_id'].split(':')[1]
    print "adding", album_url
    if 'artist_mbid' not in album:
        artist = db.artists.find_one(artist_key)
        if not artist:
            artist_url = 'http://www.cdbaby.com/Artist/' + album['artist_cdbaby_id']
            mbid = mb.add_artist({'name': album['artist']}, artist_url)
            artist = {'_id': artist_key, 'mbid': mbid}
            db.artists.save(artist)
            print 'added artist', mbid
        album['artist_mbid'] = artist['mbid']
    #pprint.pprint(album)
    edit_note = album_url
    mbid = mb.add_release(album, edit_note)
    mb.add_url('release', mbid, 78, album_url)
    album['mbid'] = mbid
    album['status']['imported'] = True
    db.albums.save(album)
    print 'added release', mbid

    #form = album_to_form(album)
    #print '<form action="http://musicbrainz.org/release/add" method="post">'
    #for name, value in form.iteritems():
    #    print '<input type="hidden" name="%s" value="%s" />' % (html_escape(name), html_escape(unicode(value)))
    #print '<input type="submit" value="Add Release">'
    #print '</form>'

