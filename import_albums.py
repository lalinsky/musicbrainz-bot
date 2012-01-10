import re
import sys
import urllib2
import config
import pymongo
import pprint
from BeautifulSoup import BeautifulSoup
from guesscase import guess_case, guess_case_title


opener = urllib2.build_opener()
if config.WWW_USER_AGENT:
    opener.addheaders = [('User-Agent', config.WWW_USER_AGENT)]


mongo = pymongo.Connection()
db = mongo.mbot


for album in db.albums.find({'status': {'imported': False}}):
    artist_key = 'cdbaby:' + album['artist_cdbaby_id']
    artist = db.artists.find_one(artist_key)
    print artist['mbid']
    print album

