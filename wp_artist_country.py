import os
import re
import sqlalchemy
import solr
from simplemediawiki import MediaWiki
from editing import MusicBrainzClient
import pprint
import urllib
import time
from utils import mangle_name, join_names, mw_remove_markup
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

wp = MediaWiki('http://en.wikipedia.org/w/api.php')
wps = solr.SolrConnection('http://localhost:8983/solr/wikipedia')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

query = """
SELECT DISTINCT a.id, a.gid, a.name, a.country, u.url
FROM s_artist a
JOIN l_artist_url l ON l.entity0 = a.id AND l.link IN (SELECT id FROM link WHERE link_type = 179)
JOIN url u ON u.id = l.entity1
LEFT JOIN bot_wp_artist_country b ON a.gid = b.gid
WHERE
    b.gid IS NULL AND
    a.country IS NULL AND
    u.url LIKE 'http://en.wikipedia.org/wiki/%%'
ORDER BY a.id
LIMIT 10000
"""


def get_page_content_from_cache(title):
    key = title.encode('ascii', 'xmlcharrefreplace').replace('/', '_')
    file = os.path.join('enwiki-cache', key[0], key)
    if os.path.exists(file):
        return open(file).read().decode('utf8')


def add_page_content_to_cache(title, content):
    key = title.encode('ascii', 'xmlcharrefreplace').replace('/', '_')
    dir = os.path.join('enwiki-cache', key[0])
    if not os.path.exists(dir):
        os.mkdir(dir)
    file = os.path.join(dir, key)
    f = open(file, 'w')
    f.write(content.encode('utf8'))
    f.close()


def get_page_content(wp, title):
    content = get_page_content_from_cache(title)
    if content:
        return content
    resp = wp.call({'action': 'query', 'prop': 'revisions', 'titles': title, 'rvprop': 'content'})
    pages = resp['query']['pages'].values()
    if not pages or 'revisions' not in pages[0]:
        return None
    content = pages[0]['revisions'][0].values()[0]
    add_page_content_to_cache(title, content)
    return content


def extract_page_title(url):
    prefix = 'http://en.wikipedia.org/wiki/'
    if not url.startswith(prefix):
        return None
    return urllib.unquote(url[len(prefix):].encode('utf8')).decode('utf8')


category_re = re.compile(r'\[\[Category:(.+?)\]\]')
infobox_re = re.compile(r'\{\{Infobox (musical artist|person)[^|]*((?:[^{}].*?|\{\{.*?\}\})*)\}\}', re.DOTALL)

link_countries = {
    'Afghanistan': 'AF',
    'Albania': 'AL',
    'Algeria': 'DZ',
    'American Samoa': 'AS',
    'Andorra': 'AD',
    'Angola': 'AO',
    'Anguilla': 'AI',
    'Antarctica': 'AQ',
    'Antigua and Barbuda': 'AG',
    'Argentina': 'AR',
    'Armenia': 'AM',
    'Aruba': 'AW',
    'Australia': 'AU',
    'Austria': 'AT',
    'Azerbaijan': 'AZ',
    'Bahamas': 'BS',
    'Bahrain': 'BH',
    'Bangladesh': 'BD',
    'Barbados': 'BB',
    'Belarus': 'BY',
    'Belgium': 'BE',
    'Belize': 'BZ',
    'Benin': 'BJ',
    'Bermuda': 'BM',
    'Bhutan': 'BT',
    'Bolivia': 'BO',
    'Bosnia and Herzegovina': 'BA',
    'Botswana': 'BW',
    'Bouvet Island': 'BV',
    'Brazil': 'BR',
    'Brazilia': 'BR',
    'Brisbane': 'AU',
    'British Indian Ocean Territory': 'IO',
    'Brunei Darussalam': 'BN',
    'Bulgaria': 'BG',
    'Burkina Faso': 'BF',
    'Burundi': 'BI',
    'Cambodia': 'KH',
    'Cameroon': 'CM',
    'Canada': 'CA',
    'Canadians': 'CA',
    'Cape Verde': 'CV',
    'Cayman Islands': 'KY',
    'Central African Republic': 'CF',
    'Chad': 'TD',
    'Chile': 'CL',
    'China': 'CN',
    'Christmas Island': 'CX',
    'Cocos (Keeling) Islands': 'CC',
    'Colombia': 'CO',
    'Comoros': 'KM',
    'Congo': 'CG',
    'Congo, The Democratic Republic of the': 'CD',
    'Cook Islands': 'CK',
    'Costa Rica': 'CR',
    'Croatia': 'HR',
    'Cuba': 'CU',
    'Cyprus': 'CY',
    'Czech Republic': 'CZ',
    'Denmark': 'DK',
    'Djibouti': 'DJ',
    'Dominica': 'DM',
    'East Germany': 'DE',
    'Ecuador': 'EC',
    'Egypt': 'EG',
    'El Salvador': 'SV',
    'England': 'GB',
    'Equatorial Guinea': 'GQ',
    'Eritrea': 'ER',
    'Estonia': 'EE',
    'Ethiopia': 'ET',
    'Falkland Islands (Malvinas)': 'FK',
    'Faroe Islands': 'FO',
    'Fiji': 'FJ',
    'Finland': 'FI',
    'France': 'FR',
    'French Guiana': 'GF',
    'French Polynesia': 'PF',
    'French Southern Territories': 'TF',
    'Gabon': 'GA',
    'Gambia': 'GM',
    'Georgia': 'GE',
    'Germany': 'DE',
    'Ghana': 'GH',
    'Gibraltar': 'GI',
    'Greece': 'GR',
    'Greenland': 'GL',
    'Grenada': 'GD',
    'Guadeloupe': 'GP',
    'Guam': 'GU',
    'Guatemala': 'GT',
    'Guernsey': 'GG',
    'Guinea-Bissau': 'GW',
    'Guinea': 'GN',
    'Guyana': 'GY',
    'Haiti': 'HT',
    'Heard Island and McDonald Islands': 'HM',
    'Honduras': 'HN',
    'Hong Kong': 'HK',
    'Hungary': 'HU',
    'Iceland': 'IS',
    'India': 'IN',
    'Indonesia': 'ID',
    'Iran, Islamic Republic of': 'IR',
    'Iraq': 'IQ',
    'Ireland': 'IE',
    'Isle of Man': 'IM',
    'Israel': 'IL',
    'Italian people': 'IT',
    'Italy': 'IT',
    'Jamaica': 'JM',
    'Japan': 'JP',
    'Tokyo': 'JP',
    'Jersey': 'JE',
    'Jordan': 'JO',
    'Kazakhstan': 'KZ',
    'Kenya': 'KE',
    'Kingdom of the Netherlands': 'NL',
    'Kiribati': 'KI',
    'Korea (South), Republic of': 'KR',
    'Kuwait': 'KW',
    'Kyrgyzstan': 'KG',
    'Latvia': 'LV',
    'Lebanon': 'LB',
    'Lesotho': 'LS',
    'Liberia': 'LR',
    'Libyan Arab Jamahiriya': 'LY',
    'Liechtenstein': 'LI',
    'Lithuania': 'LT',
    'London, England': 'GB',
    'London': 'GB',
    'Luxembourg': 'LU',
    'Macao': 'MO',
    'Macedonia, The Former Yugoslav Republic of': 'MK',
    'Madagascar': 'MG',
    'Malawi': 'MW',
    'Malaysia': 'MY',
    'Maldives': 'MV',
    'Mali': 'ML',
    'Malta': 'MT',
    'Manchester': 'GB',
    'Marshall Islands': 'MH',
    'Martinique': 'MQ',
    'Mauritania': 'MR',
    'Mauritius': 'MU',
    'Mayotte': 'YT',
    'Mexico': 'MX',
    'Micronesia, Federated States of': 'FM',
    'Moldova': 'MD',
    'Monaco': 'MC',
    'Mongolia': 'MN',
    'Montenegro': 'ME',
    'Montserrat': 'MS',
    'Morocco': 'MA',
    'Mozambique': 'MZ',
    'Myanmar': 'MM',
    'Namibia': 'NA',
    'Nauru': 'NR',
    'Nepal': 'NP',
    'Netherlands Antilles': 'AN',
    'Netherlands': 'NL',
    'New Caledonia': 'NC',
    'New Zealand': 'NZ',
    'Nicaragua': 'NI',
    'Nigeria': 'NG',
    'Niger': 'NE',
    'Niue': 'NU',
    'Norfolk Island': 'NF',
    'Northern Mariana Islands': 'MP',
    'Norway': 'NO',
    'Oman': 'OM',
    'Pakistan': 'PK',
    'Palau': 'PW',
    'Palestinian Territory': 'PS',
    'Panama': 'PA',
    'Papua New Guinea': 'PG',
    'Paraguay': 'PY',
    'Peru': 'PE',
    'Philippines': 'PH',
    'Pitcairn': 'PN',
    'Poland': 'PL',
    'Portugal': 'PT',
    'Puerto Rico': 'PR',
    'Qatar': 'QA',
    'Reunion': 'RE',
    'Romania': 'RO',
    'Russian Federation': 'RU',
    'Rwanda': 'RW',
    'Saint Barthelemy': 'BL',
    'Saint Helena': 'SH',
    'Saint Kitts and Nevis': 'KN',
    'Saint Lucia': 'LC',
    'Saint Martin': 'MF',
    'Saint Pierre and Miquelon': 'PM',
    'Saint Vincent and The Grenadines': 'VC',
    'Samoa': 'WS',
    'San Marino': 'SM',
    'Sao Tome and Principe': 'ST',
    'Saudi Arabia': 'SA',
    'Scotland': 'GB',
    'Senegal': 'SN',
    'Serbia and Montenegro': 'CS',
    'Serbia': 'RS',
    'Seychelles': 'SC',
    'Sierra Leone': 'SL',
    'Singapore': 'SG',
    'Slovakia': 'SK',
    'Slovenia': 'SI',
    'Solomon Islands': 'SB',
    'Somalia': 'SO',
    'South Africa': 'ZA',
    'South Georgia and the South Sandwich Islands': 'GS',
    'Spain': 'ES',
    'Sri Lanka': 'LK',
    'Sudan': 'SD',
    'Suriname': 'SR',
    'Svalbard and Jan Mayen': 'SJ',
    'Swaziland': 'SZ',
    'Sweden': 'SE',
    'Switzerland': 'CH',
    'Syrian Arab Republic': 'SY',
    'Taiwan': 'TW',
    'Tajikistan': 'TJ',
    'Tanzania, United Republic of': 'TZ',
    'Thailand': 'TH',
    'Timor-Leste': 'TL',
    'Togo': 'TG',
    'Tokelau': 'TK',
    'Tonga': 'TO',
    'Trinidad and Tobago': 'TT',
    'Tunisia': 'TN',
    'Turkey': 'TR',
    'Turkmenistan': 'TM',
    'Turks and Caicos Islands': 'TC',
    'Tuvalu': 'TV',
    'Uganda': 'UG',
    'Ukraine': 'UA',
    'United Arab Emirates': 'AE',
    'United Kingdom': 'GB',
    'United Kingdom': 'GB',
    'United States Minor Outlying Islands': 'UM',
    'United States': 'US',
    'Uruguay': 'UY',
    'USA': 'US',
    'Uzbekistan': 'UZ',
    'Vanuatu': 'VU',
    'Vatican City State (Holy See)': 'VA',
    'Venezuela': 'VE',
    'Viet Nam': 'VN',
    'Virgin Islands, British': 'VG',
    'Virgin Islands, U.S.': 'VI',
    'Wales': 'GB',
    'Wallis and Futuna': 'WF',
    'Western Sahara': 'EH',
    'Yemen': 'YE',
    'Yugoslavia': 'YU',
    'Zambia': 'ZM',
    'Korean': 'ZW',
}

link_us_states = [
    'Alabama',
    'Alaska',
    'Arizona',
    'Arkansas',
    'California',
    'Colorado',
    'Connecticut',
    'Delaware',
    'Florida',
    'Georgia',
    'Hawaii',
    'Idaho',
    'Illinois',
    'Indiana',
    'Iowa',
    'Kansas',
    'Kentucky',
    'Louisiana',
    'Maine',
    'Maryland',
    'Massachusetts',
    'Michigan',
    'Minnesota',
    'Mississippi',
    'Missouri',
    'Montana',
    'Nebraska',
    'Nevada',
    'New Hampshire',
    'New Jersey',
    'New Mexico',
    'New York',
    'North Carolina',
    'North Dakota',
    'Ohio',
    'Oklahoma',
    'Oregon',
    'Pennsylvania',
    'Rhode Island',
    'South Carolina',
    'South Dakota',
    'Tennessee',
    'Texas',
    'Utah',
    'Vermont',
    'Virginia',
    'Washington',
    'Washington D.C.',
    'Washington, D.C.',
    'West Virginia',
    'Wisconsin',
    'Wyoming',
]

category_countries = {
    'American': 'US',
    'English': 'GB',
    'British': 'GB',
    'Scottish': 'GB',
    'Welch': 'GB',
    'Belgian': 'BE',
    'Dutch': 'NL',
    'French': 'FR',
    'Polish': 'PL',
    'Swiss': 'CH',
    'Italian': 'IT',
    'Pakistani': 'PK',
    'Spanish': 'ES',
    'German': 'DE',
    'Greek': 'GR',
    'Australian': 'AU',
    'Canadian': 'CA',
    'Indonesian': 'ID',
    'Swedish': 'SE',
    'Brazilian': 'BR',
    'Irish': 'IE',
    'Korean': 'KR',
    'Japanese': 'JP',
    'Chinese': 'CN',
    'Russian': 'RU',
    'Hungarian': 'HU',
    'Slovak': 'SK',
    'Czech': 'CZ',
    'Ukrainian': 'UA',
    'Turkish': 'TR',
    'Romanian': 'RO',
    'Polish': 'PL',
    'Portugal': 'PT',
    'Norwegian': 'NO',
    'Mexican': 'MX',
    'Latvian': 'LV',
    'Estonian': 'EE',
    'Finnish': 'FI',
    'Austrian': 'AT',
    'Israeli': 'IL',
    'South African': 'ZA',
    'Puerto Rican': 'PR',
    'Senegalese': 'SN',
    'Croatian': 'HR',
    'Danish': 'DK',
    'Icelandic': 'IS',
    'Jamaican': 'JM',
    'New Zealand': 'NZ',
    'Algerian': 'DZ',
    'Cuban': 'CU',
    'Hong Kong': 'HK',
}


def parse_infobox(page):
    match = infobox_re.search(page)
    info = {}
    if match is None:
        return info
    info['_type'] = match.group(1)
    for line in match.group(2).splitlines():
        if '=' not in line:
            continue
        name, value = tuple(s.strip() for s in line.split('=', 1))
        info[name.lstrip('| ').lower()] = value
    return info


def extract_first_paragraph(page):
    page = mw_remove_markup(page)
    return page.strip().split('\n\n')[0]


def determine_country_from_categories(page):
    countries = set()
    relevant_categories = []
    categories = category_re.findall(page)
    for category in categories:
        category = category.replace('_', ' ')
        for name, code in category_countries.iteritems():
            if category.startswith(name + ' '):
                countries.add(code)
                relevant_categories.append(category)
    reason = 'Belongs to %s.' % join_names('category', relevant_categories)
    return countries, reason


def find_countries_in_text(countries, relevant_links, text):
    text = text.replace('_', ' ')
    for name, code in link_countries.iteritems():
        for name in [name, name.lower()]:
            if '[[' + name + ']]' in text or '[[' + name + '|' in text:
                countries.add(code)
                relevant_links.append(name)
                break
    for name in link_us_states:
        m = re.search(r'\[\[(([^\]\|]+, )?%s)(\]\]|\|)' % (re.escape(name),), text)
        if m is not None:
            countries.add('US')
            relevant_links.append(m.group(1))


def determine_country_from_infobox(infobox):
    countries = set()
    relevant_links = []
    for field in ['origin', 'born', 'birth_place']:
        text = infobox.get(field, '')
        find_countries_in_text(countries, relevant_links, text)
    reason = 'Infobox links to %s.' % join_names('', relevant_links)
    return countries, reason


def determine_country_from_text(page):
    countries = set()
    relevant_links = []
    text = extract_first_paragraph(page)
    #print text
    find_countries_in_text(countries, relevant_links, text)
    reason = 'The first paragraph links to %s.' % join_names('', relevant_links)
    return countries, reason


country_ids = {}
for id, code in db.execute("SELECT id, iso_code FROM country"):
    country_ids[code] = id

seen = set()
for artist in db.execute(query):
    if artist['id'] in seen:
        continue
    seen.add(artist['id'])
    print 'Looking up artist "%s" http://musicbrainz.org/artist/%s' % (artist['name'], artist['gid'])
    print ' * wiki:', artist['url']
    page_title = extract_page_title(artist['url'])
    page = get_page_content(wp, page_title) or ''
    infobox = parse_infobox(page)
    all_countries = set()
    all_reasons = []
    countries, reason = determine_country_from_infobox(infobox)
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
    countries, reason = determine_country_from_text(page)
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
    countries, reason = determine_country_from_categories(page)
    has_categories = False
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
        has_categories = True
    can_add = True
    if len(all_reasons) < 2 or not all_countries or not has_categories:
        print ' * not enough sources', all_countries, all_reasons
        can_add = False
    if len(all_countries) > 1:
        print ' * conflicting countries', all_countries, all_reasons
        can_add = False
    if can_add:
        country = list(all_countries)[0]
        all_reasons = ['From %s.' % (artist['url'],)] + all_reasons
        edit_note = ' '.join(all_reasons)
        print ' * country:', country, country_ids[country]
        print ' * edit note:', edit_note
        #time.sleep(1)
        mb.set_artist_country(artist['gid'], country_ids[country], edit_note)
    db.execute("INSERT INTO bot_wp_artist_country (gid) VALUES (%s)", (artist['gid'],))
    print

