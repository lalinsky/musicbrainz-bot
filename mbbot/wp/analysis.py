# -*- coding: utf-8 -*-

import re
import locale
import calendar
from mbbot.data.countries import wp_country_links, wp_us_states_links, demonyms
from mbbot.data.firstnames import firstname_gender
from utils import join_names, out, colored_out, bcolors

pronouns_re = {}
pronouns_re['en'] = re.compile(r'\b(he|she|her|his)\b', re.I)
pronouns_re['fr'] = re.compile(r'\b(il|elle)\b', re.I)
pronouns_female = {}
pronouns_female['en'] = ('she', 'her')
pronouns_female['fr'] = ('elle')

infobox_fields = {}
infobox_fields['country'] = {}
infobox_fields['country']['en'] = ['origin', 'born', 'birth_place']
infobox_fields['country']['fr'] = ['naissance lieu', 'décès lieu', 'nationalité', 'pays origine']

infobox_fields['begin_date'] = {}
infobox_fields['begin_date']['en'] = 'birth_date'
infobox_fields['begin_date']['fr'] = 'naissance'
infobox_fields['end_date'] = {}
infobox_fields['end_date']['en'] = 'death_date'
infobox_fields['end_date']['fr'] = 'décès'

infobox_fields['background'] = {}
infobox_fields['background']['en'] = 'background'
infobox_fields['background']['fr'] = 'charte'

date_template_re = { 'begin_date': {}, 'end_date': {} }
date_template_re['begin_date']['en'] = re.compile(r'{{(?:Birth date and age|Birth date|Bda|dob)\|(?P<year>\d+)\|(?P<month>[\d\w]+)\|(?P<day>\d+)', re.I)
date_template_re['begin_date']['fr'] = re.compile(r'{{Date de naissance\|(?P<day>\d+)\|(?P<month>[\d\w]+)\|(?P<year>\d+)', re.I)
date_template_re['end_date']['en'] = re.compile(r'{{(?:Death date and age|Dda)\|(?P<year>\d+)\|(?P<month>[\d\w]+)\|(?P<day>\d+)', re.I)
date_template_re['end_date']['fr'] = re.compile(r'{{Date de d\xe9c\xe8s\|(?P<day>\d+)\|(?P<month>[\d\w]+)\|(?P<year>\d+)', re.I)

date_categories_re = {'person': {'begin': {}, 'end': {}}, 'group': {'begin': {}, 'end': {}}}
date_categories_re['person']['begin']['en'] = re.compile(r'(\d{4}) births', re.I)
date_categories_re['person']['end']['en'] = re.compile(r'(\d{4}) deaths', re.I)
date_categories_re['group']['begin']['en'] = re.compile(r'Musical groups established in (\d{4})', re.I)
date_categories_re['person']['end']['en'] = re.compile(r'Musical groups disestablished in (\d{4})', re.I)
date_categories_re['person']['begin']['fr'] = re.compile(r'Naissance en (\d{4})', re.I)
date_categories_re['person']['end']['fr'] = re.compile(r'D\xe9c\xe8s en (\d{4})', re.I)
date_categories_re['group']['begin']['fr'] = re.compile(r'Groupe de musique form\xe9 en (\d{4})', re.I)

locales = {
    'fr': 'fr_FR.UTF-8',
    'en': 'en_US.UTF-8'
}

##################################### Country ###########################################

def determine_country(page):
    all_countries = set()
    all_reasons = []
    countries, reason = determine_country_from_infobox(page)
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
    countries, reason = determine_country_from_text(page)
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
    countries, reason, category_count = determine_country_from_categories(page)
    has_categories = False
    if countries:
        all_countries.update(countries)
        all_reasons.append(reason)
        has_categories = True
    if len(all_reasons) < 1 or not all_countries or not has_categories:
        colored_out(bcolors.WARNING, ' * not enough sources for countries', all_countries, all_reasons)
        return None, []
    if len(all_countries) > 1:
        colored_out(bcolors.FAIL, ' * conflicting countries', all_countries, all_reasons)
        return None, []
    country = list(all_countries)[0]
    colored_out(bcolors.OKGREEN, ' * new country: ', country)
    return country, all_reasons

def determine_country_from_categories(page):
    countries = set()
    relevant_categories = []
    for category in page.categories:
        category = category.replace('_', ' ')
        for name, code in demonyms[page.lang].iteritems():
            if name.decode('utf8') in category:
                countries.add(code)
                relevant_categories.append(category)
        for name in wp_us_states_links:
            if category.endswith('from ' + name):
                countries.add('US')
                relevant_categories.append(category)
    reason = 'Belongs to %s.' % join_names('category', relevant_categories)
    return countries, reason, len(relevant_categories)

def find_countries_in_text(countries, relevant_links, text, lang):
    text = text.replace('_', ' ')
    for name, code in wp_country_links[lang].iteritems():
        for name in [name.decode('utf8'), name.decode('utf8').lower()]:
            if '[[' + name + ']]' in text or '[[' + name + '|' in text or '{{' + name + '}}' in text:
                countries.add(code)
                relevant_links.append(name)
                break
    for name in wp_us_states_links:
        m = re.search(r'\[\[(([^\]\|]+, )?%s)(\]\]|\|)' % (re.escape(name),), text)
        if m is not None:
            countries.add('US')
            relevant_links.append(m.group(1))


def determine_country_from_infobox(page):
    countries = set()
    relevant_links = []
    for field in infobox_fields['country'][page.lang]:
        field = field.decode('utf8')
        text = page.infobox.get(field, '')
        #if len(text) > 0:
        #    out("Text from infobox (field=%s): %s" % (field, text))
        find_countries_in_text(countries, relevant_links, text, page.lang)
    reason = 'Infobox links to %s.' % join_names('', relevant_links)
    return countries, reason

def determine_country_from_text(page):
    countries = set()
    relevant_links = []
    find_countries_in_text(countries, relevant_links, page.abstract, page.lang)
    reason = 'The first paragraph links to %s.' % join_names('', relevant_links)
    return countries, reason

##################################### Artist gender ###########################################

def determine_gender(page):
    all_genders = set()
    all_reasons = []
    genders, reason = determine_gender_from_firstname(page)
    if genders:
        all_genders.update(genders)
        all_reasons.append(reason)
    genders, reason = determine_gender_from_categories(page)
    if genders:
        all_genders.update(genders)
        all_reasons.append(reason)
    genders, reason = determine_gender_from_text(page)
    if genders:
        all_genders.update(genders)
        all_reasons.append(reason)
    if not all_reasons:
        colored_out(bcolors.WARNING, ' * not enough sources for genders')
        return None, []
    if len(all_genders) > 1:
        colored_out(bcolors.FAIL, ' * conflicting genders', all_genders, all_reasons)
        return None, []
    gender = list(all_genders)[0]
    colored_out(bcolors.OKGREEN, ' * new gender:', gender)
    return gender, all_reasons

def determine_gender_from_categories(page):
    genders = set()
    relevant_categories = []
    for category in page.categories:
        if re.search(r'\bmale\b', category, re.I):
            genders.add('male')
            relevant_categories.append(category)
        if re.search(r'\bfemale\b', category, re.I):
            genders.add('female')
            relevant_categories.append(category)
        if re.search(r'^(Chanteur|Acteur|Animateur)\b', category, re.I):
            genders.add('male')
            relevant_categories.append(category)
        if re.search(r'^(Chanteuse|Actrice|Animatrice)\b', category, re.I):
            genders.add('female')
            relevant_categories.append(category)
    reason = 'Belongs to %s.' % join_names('category', relevant_categories)
    return genders, reason


def determine_gender_from_text(page):
    pronouns = pronouns_re[page.lang].findall(page.text)
    num_male_pronouns = 0
    num_female_pronouns = 0
    for pronoun in pronouns:
        if pronoun.lower() in pronouns_female[page.lang]:
            num_female_pronouns += 1
        else:
            num_male_pronouns += 1
    if num_male_pronouns > 2 and num_female_pronouns == 0:
        return ['male'], 'The first paragraph uses male pronouns %s times.' % (num_male_pronouns,)
        genders.add('male')
    elif num_female_pronouns > 2 and num_male_pronouns == 0:
        return ['female'], 'The first paragraph uses female pronouns %s times.' % (num_female_pronouns,)
    return None, ''

def determine_gender_from_firstname(page):
    m = re.match(r'^(\S+)\s', page.title.replace('_', ' '))
    if m is not None:
        firstname = m.group(1).encode('utf8')
        if page.lang in firstname_gender:
            firstnames = firstname_gender[page.lang]

            if firstname in firstname_gender[page.lang]:
                gender = firstname_gender[page.lang][firstname]
                return [gender], 'First name "%s" is a %s first name.' % (firstname.decode('utf8'), gender)

            # if first name is a compound name, get first part
            m = re.match(r'^([^-]+)-', firstname)
            firstname_prefix = ''
            if m is not None:
                firstname_prefix = m.group(1)

            if page.lang == 'fr' and firstname_prefix in firstname_gender[page.lang]:
                gender = firstname_gender[page.lang][firstname_prefix]
                return [gender], 'First name "%s" is a %s first name.' % (firstname.decode('utf8'), gender)
    return None, ''

##################################### Artist type ###########################################

def determine_type(page):
    all_types = set()
    all_reasons = []
    types, reason = determine_type_from_page(page)
    if types:
        all_types.update(types)
        all_reasons.append(reason)
    if not all_reasons:
        colored_out(bcolors.WARNING, ' * not enough sources for types')
        return None, []
    if len(all_types) > 1:
        colored_out(bcolors.FAIL, ' * conflicting types', all_types, all_reasons)
        return None, []
    type = list(all_types)[0]
    colored_out(bcolors.OKGREEN, ' * new type:', type)
    return type, all_reasons

def determine_type_from_page(page):
    types = set()
    reasons = []
    background_field = infobox_fields['background'][page.lang]
    background = page.infobox.get(background_field, '')
    if background == 'solo_singer' or background == 'vocal' or background == 'instrumentiste':
        types.add('person')
        reasons.append('Infobox has "'+background_field+' = '+background+'".')
    if page.persondata.get('name'):
        types.add('person')
        reasons.append('Contains the "Persondata" infobox.')
    if background == 'group_or_band' or background == 'groupe':
        types.add('group')
        reasons.append('Infobox has "'+background_field+' = '+background+'".')
    relevant_categories = []
    for category in page.categories:
        if page.lang == 'fr':
            if category.startswith('Groupe'):
                types.add('group')
                relevant_categories.append(category)
        else:
            if category.endswith('groups') or category.startswith('Musical groups'):
                types.add('group')
                relevant_categories.append(category)

    if relevant_categories:
        reasons.append('Belongs to %s.' % join_names('category', relevant_categories))
    return types, ' '.join(reasons)


##################################### Dates ###########################################

def determine_begin_date(artist, page, is_performance_name):
    empty_date = {'year': None, 'month': None, 'day': None}
    if artist['type'] == 1 and not is_performance_name:
        date, reasons = determine_date_from_persondata(page.persondata, 'date of birth')
        if date['year']:
            return date, reasons
        date, reasons = determine_date_from_infobox(page, 'begin_date')
        if date['year']:
            return date, reasons
        relevant_categories = []
        if page.lang not in date_categories_re['person']['begin']:
            return empty_date, []
        for category in page.categories:
            m = re.match(date_categories_re['person']['begin'][page.lang], category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
    elif artist['type'] == 2:
        if page.lang not in date_categories_re['group']['begin']:
            return empty_date, []
        relevant_categories = []
        for category in page.categories:
            m = re.match(date_categories_re['group']['begin'][page.lang], category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
            m = re.match(r'Groupe de musique formé en (\d{4})', category)
    return empty_date, []

def determine_end_date(artist, page, is_performance_name):
    empty_date = {'year': None, 'month': None, 'day': None}
    if artist['type'] == 1 and not is_performance_name:
        date, reasons = determine_date_from_persondata(page.persondata, 'date of death')
        if date['year']:
            return date, reasons
        date, reasons = determine_date_from_infobox(page, 'end_date')
        if date['year']:
            return date, reasons
        if page.lang not in date_categories_re['person']['end']:
            return empty_date, []
        relevant_categories = []
        for category in page.categories:
            m = re.match(date_categories_re['person']['end'][page.lang], category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
    elif artist['type'] == 2:
        if page.lang not in date_categories_re['group']['end']:
            return empty_date, []
        relevant_categories = []
        for category in page.categories:
            m = re.match(date_categories_re['group']['begin'][page.lang], category)
            if m is not None:
                return {'year': int(m.group(1)), 'month': None, 'day': None}, ['Belongs to category "%s"' % category]
    return empty_date, []

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

def determine_date_from_infobox(page, date_type):
    date = {'year': None, 'month': None, 'day': None}
    if (date_type not in infobox_fields) or (page.lang not in infobox_fields[date_type]):
        return date, []

    field = infobox_fields[date_type][page.lang].decode('utf8')
    info = page.infobox.get(field, '')
    m = date_template_re[date_type][page.lang].match(info)
    if m is not None:
        date = {'year': int(m.group('year')), 'day': int(m.group('day'))}
        if m.group('month').isdigit():
            date['month'] = int(m.group('month'))
        else:
            try:
                locale.setlocale(locale.LC_ALL, locales[page.lang])
                month_number = dict((v,k) for k,v in enumerate(calendar.month_name))
                date['month'] = month_number[m.group('month').lower()]
            except ValueError:
                date['month'] = None
        return date, ['Infobox has %s.' % info]
    return date, []
