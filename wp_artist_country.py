import os
import datetime
import re
import sqlalchemy
import solr
from simplemediawiki import MediaWiki
from editing import MusicBrainzClient
import pprint
import urllib
import time
from utils import mangle_name, join_names, mw_remove_markup, out
import config as cfg

engine = sqlalchemy.create_engine(cfg.MB_DB)
db = engine.connect()
db.execute("SET search_path TO musicbrainz")

wp = MediaWiki('http://en.wikipedia.org/w/api.php')
wps = solr.SolrConnection('http://localhost:8983/solr/wikipedia')

mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)

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
    u.url LIKE 'http://en.wikipedia.org/wiki/%%'
ORDER BY a.id
LIMIT 10000
"""

performance_name_query = """
SELECT count(*) FROM l_artist_artist
WHERE link IN (SELECT id FROM link WHERE link_type = 108)
AND entity1 = %s
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


category_re = re.compile(r'\[\[Category:(.+?)(?:\|.*?)?\]\]')
infobox_re = re.compile(r'\{\{Infobox (musical artist|person)[^|]*((?:[^{}].*?|\{\{.*?\}\})*)\}\}', re.DOTALL)
persondata_re = re.compile(r'\{\{Persondata[^|]*((?:[^{}].*?|\{\{.*?\}\})*)\}\}', re.DOTALL)

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
    'Republic of the Congo': 'CG',
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
    'Repubic of Ireland': 'IE',
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
    'Singaporean': 'SG',
    'Filipino': 'PH',
    'Republic of the Congo': 'CG',
    'Mozambican': 'MZ',
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


def parse_persondata(page):
    match = persondata_re.search(page)
    info = {}
    if match is None:
        return info
    for line in match.group(1).splitlines():
        if '=' not in line:
            continue
        name, value = tuple(s.strip() for s in line.split('=', 1))
        info[name.lstrip('| ').lower()] = value
    return info


def extract_first_paragraph(page):
    page = mw_remove_markup(page)
    return page.strip().split('\n\n')[0]


def extract_page_categories(page):
    categories = category_re.findall(page)
    return categories


def determine_country_from_categories(categories):
    countries = set()
    relevant_categories = []
    for category in categories:
        category = category.replace('_', ' ')
        for name, code in category_countries.iteritems():
            if category.startswith(name + ' '):
                countries.add(code)
                relevant_categories.append(category)
        for name in link_us_states:
            if category.endswith('from ' + name):
                countries.add('US')
                relevant_categories.append(category)
    reason = 'Belongs to %s.' % join_names('category', relevant_categories)
    return countries, reason, len(relevant_categories)


def determine_gender_from_categories(categories):
    genders = set()
    relevant_categories = []
    for category in categories:
        if re.search(r'\bmale\b', category, re.I):
            genders.add('male')
            relevant_categories.append(category)
        if re.search(r'\bfemale\b', category, re.I):
            genders.add('female')
            relevant_categories.append(category)
    reason = 'Belongs to %s.' % join_names('category', relevant_categories)
    return genders, reason


def determine_gender_from_text(text):
    pronouns = re.findall(r'\b(he|she|her|his)\b', text, re.I)
    num_male_pronouns = 0
    num_female_pronouns = 0
    for pronoun in pronouns:
        if pronoun.lower() in ('she', 'her'):
            num_female_pronouns += 1
        else:
            num_male_pronouns += 1
    if num_male_pronouns > 2 and num_female_pronouns == 0:
        return ['male'], 'The first paragraph mentions "he" or "his" %s times' % (num_male_pronouns,)
        genders.add('male')
    elif num_female_pronouns > 2 and num_male_pronouns == 0:
        return ['female'], 'The first paragraph mentions "she" or "her" %s times' % (num_female_pronouns,)
    return None, ''


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


def determine_type_from_page(page):
    types = set()
    reasons = []
    background = page.infobox.get('background', '')
    if background == 'solo_singer':
        types.add('person')
        reasons.append('Infobox has "background = solo_singer".')
    if page.persondata.get('name'):
        types.add('person')
        reasons.append('Contains the "Persondata" infobox.')
    if background == 'group_or_band':
        types.add('group')
        reasons.append('Infobox has "background = group_or_band".')
    relevant_categories = []
    for category in page.categories:
        if category.endswith('groups') or category.startswith('Musical groups'):
            types.add('group')
            relevant_categories.append(category)
    if relevant_categories:
        reasons.append('Belongs to %s.' % join_names('category', relevant_categories))
    return types, ' '.join(reasons)


def determine_date_from_persondata(persondata, field):
    reasons = []
    date = {'year': None, 'month': None, 'day': None}
    value = persondata.get(field, '')
    if value:
        try:
            d = datetime.datetime.strptime(value, '%B %d, %Y')
        except ValueError:
            try:
                d = datetime.datetime.strptime(value, '%d %B %Y')
            except ValueError:
                try:
                    d = datetime.datetime.strptime(value, '%Y-%m-%d')
                except ValueError:
                    d = None
        if d:
            reasons.append('Persondata has %s "%s".' % (field, value))
            date['year'] = d.year
            date['month'] = d.month
            date['day'] = d.day
        else:
            try:
                date['year'] = int(value)
                reasons.append('Persondata has %s "%s".' % (field, value))
            except ValueError:
                pass
    return date, reasons


def determine_begin_date(artist, page, is_performance_name):
    if artist['type'] == 1 and not is_performance_name:
        date, reasons = determine_date_from_persondata(page.persondata, 'date of birth')
        if date['year']:
            return date, reasons
        relevant_categories = []
        for category in page.categories:
            m = re.match(r'(\d{4}) births', category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
    elif artist['type'] == 2:
        relevant_categories = []
        for category in page.categories:
            m = re.match(r'Musical groups established in (\d{4})', category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
    return {'year': None, 'month': None, 'day': None}, []


def determine_end_date(artist, page, is_performance_name):
    if artist['type'] == 1 and not is_performance_name:
        date, reasons = determine_date_from_persondata(page.persondata, 'date of death')
        if date['year']:
            return date, reasons
        relevant_categories = []
        for category in page.categories:
            m = re.match(r'(\d{4}) deaths', category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
    elif artist['type'] == 2:
        relevant_categories = []
        for category in page.categories:
            m = re.match(r'Musical groups disestablished in (\d{4})', category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
    return {'year': None, 'month': None, 'day': None}, []


def determine_country_from_text(page):
    countries = set()
    relevant_links = []
    find_countries_in_text(countries, relevant_links, page.abstract)
    reason = 'The first paragraph links to %s.' % join_names('', relevant_links)
    return countries, reason


country_ids = {}
for id, code in db.execute("SELECT id, iso_code FROM country"):
    country_ids[code] = id

gender_ids = {}
for id, code in db.execute("SELECT id, lower(name) FROM gender"):
    gender_ids[code] = id

artist_type_ids = {}
for id, code in db.execute("SELECT id, lower(name) FROM artist_type"):
    artist_type_ids[code] = id


class WikiPage(object):

    def __init__(self, title, text):
        self.title = title
        self.text = text
        self.categories = extract_page_categories(text)
        self.infobox = parse_infobox(text)
        self.persondata = parse_persondata(text)
        self.abstract = extract_first_paragraph(text)

    @classmethod
    def fetch(cls, url):
        page_title = extract_page_title(artist['url'])
        return cls(page_title, get_page_content(wp, page_title) or '')


def determine_country(page):
    all_countries = set()
    all_reasons = []
    countries, reason = determine_country_from_infobox(page.infobox)
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
    countries, reason = determine_country_from_text(page)
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
    countries, reason, category_count = determine_country_from_categories(page.categories)
    has_categories = False
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
        has_categories = True
    if len(all_reasons) < 1 or not all_countries or not has_categories:
        out(' * not enough sources for countries', all_countries, all_reasons)
        return None, []
    if len(all_countries) > 1:
        out(' * conflicting countries', all_countries, all_reasons)
        return None, []
    country = list(all_countries)[0]
    country_id = country_ids[country]
    out(' * new country:', country, country_id)
    return country_id, all_reasons


def determine_gender(page):
    all_genders = set()
    all_reasons = []
    genders, reason = determine_gender_from_categories(page.categories)
    if genders:
        all_genders.update(genders)
        all_reasons.append(reason)
    genders, reason = determine_gender_from_text(page.abstract)
    if genders:
        all_genders.update(genders)
        all_reasons.append(reason)
    if not all_reasons:
        out(' * not enough sources for genders')
        return None, []
    if len(all_genders) > 1:
        out(' * conflicting genders', all_genders, all_reasons)
        return None, []
    gender = list(all_genders)[0]
    gender_id = gender_ids[gender]
    out(' * new gender:', gender, gender_id)
    return gender_id, all_reasons


def determine_type(page):
    all_types = set()
    all_reasons = []
    types, reason = determine_type_from_page(page)
    if types:
        all_types.update(types)
        all_reasons.append(reason)
    if not all_reasons:
        out(' * not enough sources for types')
        return None, []
    if len(all_types) > 1:
        out(' * conflicting types', all_types, all_reasons)
        return None, []
    type = list(all_types)[0]
    type_id = artist_type_ids[type]
    out(' * new type:', type, type_id)
    return type_id, all_reasons


seen = set()
for artist in db.execute(query):
    if artist['id'] in seen:
        continue
    seen.add(artist['id'])
    out('Looking up artist "%s" http://musicbrainz.org/artist/%s' % (artist['name'], artist['gid']))
    out(' * wiki:', artist['url'])

    artist = dict(artist)
    update = set()
    reasons = []

    page = WikiPage.fetch(artist['url'])

    if not artist['country']:
        country_id, country_reasons = determine_country(page)
        if country_id:
            artist['country'] = country_id
            update.add('country')
            reasons.append(('COUNTRY', country_reasons))

    if not artist['type']:
        type_id, type_reasons = determine_type(page)
        if type_id:
            artist['type'] = type_id
            update.add('type')
            reasons.append(('TYPE', type_reasons))

    if not artist['gender'] and artist['type'] == 1:
        gender_id, gender_reasons = determine_gender(page)
        if gender_id:
            artist['gender'] = gender_id
            update.add('gender')
            reasons.append(('GENDER', gender_reasons))

    is_performance_name = False
    if artist['type'] == 1:
        is_performance_name = db.execute(performance_name_query, artist['id']).scalar() > 0
        print " * checking for performance name", is_performance_name

    if not artist['begin_date_year'] and not artist['end_date_year']:
        begin_date, begin_date_reasons = determine_begin_date(artist, page, is_performance_name)
        if begin_date['year']:
            out(" * new begin date", begin_date)
            artist['begin_date_year'] = begin_date['year']
            artist['begin_date_month'] = begin_date['month']
            artist['begin_date_day'] = begin_date['day']
            update.add('begin_date')
            reasons.append(('BEGIN DATE', begin_date_reasons))
        end_date, end_date_reasons = determine_end_date(artist, page, is_performance_name)
        if end_date['year']:
            out(" * new end date", end_date)
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
        time.sleep(60 * 2)
        mb.edit_artist(artist, update, edit_note)

    db.execute("INSERT INTO bot_wp_artist_data (gid) VALUES (%s)", (artist['gid'],))
    print

