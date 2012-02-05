import re
import sys
import urllib2
import config
import pymongo
import pprint
import time
import random
import datetime
from BeautifulSoup import BeautifulSoup
from mbbot.guesscase import guess_case, guess_case_title


opener = urllib2.build_opener()
if config.WWW_USER_AGENT:
    opener.addheaders = [('User-Agent', config.WWW_USER_AGENT)]


def get_db():
    mongo = pymongo.Connection()
    return mongo.mbot


def fetch_page(url, html=False):
    delay = random.randint(5, 60)
    print "downloading %s (after %s seconds)" % (url, delay)
    time.sleep(delay)
    data = opener.open(url).read()
    if html:
        data = BeautifulSoup(data)
    return data


def extract_barcode(s):
    m = re.search(r'(\d{12,13})', s)
    if m is None:
        return None
    return m.group(1)


def extract_artist_id(s):
    m = re.search(r'/Artist/([^/]+)', s)
    if m is None:
        return None
    return m.group(1)


def extract_album_id(s):
    m = re.search(r'/cd/([^/]+)', s)
    if m is None:
        return None
    return m.group(1)


def parse_track_length(s):
    minutes, seconds = map(int, s.split(':'))
    return minutes * 60 + seconds


def parse_track_title(s):
    m = re.match(r'^(\d+). (.+)$', s)
    track_no, track_title = m.groups()
    return int(track_no), guess_case_title(track_title)


def parse_cdbaby_album(album_id):
    url = 'http://www.cdbaby.com/cd/%s' % (album_id,)
    page = fetch_page(url, html=True)

    release = {}

    album = guess_case_title(page.find('span', {'id': 'ctl00_rightColumn_lblAlbumName'}).text)
    album_id = extract_album_id(url)
    artist = guess_case(page.find('div', {'id': 'ctl00_rightColumn_pnlArtists'}).find('span').text)
    artist_id = extract_artist_id(page.find('a', {'id': 'ctl00_breadCrumb_lnkArtist'})['href'])
    barcode = page.find('span', {'id': 'ctl00_rightColumn_lblBarcode'})
    if barcode:
        barcode = extract_barcode(barcode.text)
    release_date = int(page.find('span', {'id': 'ctl00_leftColumn_lblAlbumRelease'}).text)
    record_label = page.find('span', {'id': 'ctl00_rightColumn_lblRecordLabel'})
    if record_label:
        record_label = re.sub(r'^Record Label: ', '', record_label.text)
        if artist.lower() == record_label.lower():
            record_label = None

    release = {
        'cdbaby_id': album_id,
        'title': album,
        'artist': artist,
        'artist_cdbaby_id': artist_id,
        'barcode': barcode,
        'date': str(release_date),
    }
    if record_label:
        release['label'] = record_label

    medium = {
        'position': 1,
        'tracks': [],
    }
    release['mediums'] = [medium]
    for tr in page.find('table', {'id': 'tracks-display'}).findAll('tr'):
        tds = tr.findAll('td')
        if len(tds) != 4:
            continue
        track_no, track_title = parse_track_title(tds[1].text)
        track_length = parse_track_length(tds[2].find('span').text)
        medium['tracks'].append({
            'position': track_no,
            'title': track_title,
            'length': track_length,
        })

    if page.find('input', {'class': 'cd-buynow-button'}):
        medium['format'] = 'CD'
    else:
        medium['format'] = 'Digital Media'

    return release


def find_new_cdbaby_albums(page=1):
    url = 'http://www.cdbaby.com/New'
    if page > 1:
        url += '/p%d' % page
    db = get_db()
    page = fetch_page(url, html=True)
    for a in page.findAll('a', {'class': 'overlay-link'}):
        album_id = extract_album_id(a['href'])
        if album_id is not None:
            key = 'cdbaby:' + album_id
            if not db.albums.find_one(key):
                yield album_id
            else:
                print 'already have', album_id


def fetch_cdbaby_album(album_id):
    db = get_db()
    key = 'cdbaby:' + album_id
    if not db.albums.find_one(key):
        album = parse_cdbaby_album(album_id)
        album['_id'] = key
        album['status'] = {'imported': False, 'added': datetime.datetime.now()}
        db.albums.save(album)


def fetch_new_cdbaby_albums(limit=10, pages_limit=5):
    albums = 0
    page = 1
    while albums < limit and page <= pages_limit:
        for album_id in find_new_cdbaby_albums(page):
            fetch_cdbaby_album(album_id)
            albums += 1
        page += 1


def main():
    mongo = pymongo.Connection()
    db = mongo.mbot

    url = sys.argv[1]
    key = 'cdbaby:' + extract_album_id(url)

    release = db.albums.find_one(key)
    if release is None:
        release = parse_cdbaby_album(url)
        release['_id'] = key
        release['status'] = {
            'imported': False,
        }
        db.albums.save(release)


    artist_key = 'cdbaby:' + release['artist_cdbaby_id']
    artist = db.artists.find_one(artist_key)
    if artist is None:
        artist = {'_id': artist_key}
        db.artists.save(artist)

    pprint.pprint(release)

