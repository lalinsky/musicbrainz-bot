import re

lowercase_words = set('''
    a an the
    and but or nor
    as at by for in of on to but cum mid off per qua re up via
    to
'''.split())


lowercase_extra_title_info = [
    'feat.',
    'live',
    'mix',
    'remix',
    'edit',
    'version',
    'album version',
    'bonus track',
    'radio edit'
]


def is_word(s):
    return bool(re.match(r'\w+', s))


def join_apostrophe_words(words):
    while True:
        num_words = len(words)
        for i in xrange(1, len(words) - 1):
            if words[i] == "'" and is_word(words[i-1]) and is_word(words[i+1]):
                words[i-1:i+2] = [''.join(words[i-1:i+2])]
                break
        else:
            return words


def split_words(s):
    words = re.split(r'(\W+)', s)
    words = join_apostrophe_words(words)
    return words


def guess_case_extra_title_info(s):
    def lower(m):
        return m.group(1) + m.group(2).lower() + m.group(3)
    for word in lowercase_extra_title_info:
        s = re.sub(r'(^| )(%s)($| )' % (re.escape(word),), lower, s, flags=re.I)
    return s


def guess_case_title(s):
    s = guess_case(s)
    def fix_extra_title_info(m):
        return ' (' + guess_case_extra_title_info(m.group(1)) + ')'
    return re.sub(r' \(([^)]+)\)$', fix_extra_title_info, s)


def guess_case(s):
    words = split_words(s)
    num_words = len(words)
    for i in xrange(num_words):
        word = words[i]
        if re.match(r'\w+', word):
            if i == 0 or i == num_words - 1 or word.lower() not in lowercase_words:
                if not word.isupper():
                    word = word[0].upper() + word[1:]
            else:
                word = word.lower()
        words[i] = word
    return ''.join(words)


def is_given_name(name):
    # http://www.census.gov/genealogy/names/dist.male.first
    # http://www.census.gov/genealogy/names/dist.female.first
    names = getattr(is_given_name, 'names', None)
    if names is None:
        names = set()
        for gender in ('male', 'female'):
            names.update([l.split()[0].lower() for l in open('dist.' + gender + '.first')])
        is_given_name.names = names
    return name.lower() in names


def guess_artist_sort_name(name):
    parts = split_words(guess_case(name))
    if len(parts) == 3 and is_given_name(parts[0]) and parts[1] == ' ':
        return '%s, %s' % (parts[2], parts[0])
    if parts[0] in ('The', 'A'):
        return '%s, %s' % (''.join(parts[1:]).strip(), parts[0])
    return ''.join(parts)


if __name__ == '__main__':
    assert is_given_name('juliet') == True
    assert is_given_name('the xxx') == False
    assert guess_artist_sort_name('The XX') == 'XX, The'
    assert guess_artist_sort_name('Juliet Wallin') == 'Wallin, Juliet'
    assert guess_case("That's it") == "That's It", guess_case("That's it")
    assert guess_case("That's ain't it") == "That's Ain't It", guess_case("That's ain't it")
    assert guess_case("That' it") == "That' It", guess_case("That' it")
    assert guess_case_title("That' it (RADIO EDIT)") == "That' It (radio edit)", guess_case_title("That' it (RADIO EDIT)")
    assert guess_case_title("That' it (feat. DMX)") == "That' It (feat. DMX)", guess_case_title("That' it (feat. DMX)")

