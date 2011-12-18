import re
import locale
import sys


def mangle_name(s):
    s = s.lower()
    return re.sub(r'\W', '', s, flags=re.UNICODE)


def join_names(type, strings):
    if not strings:
        return ''
    if len(strings) > 1:
        if type == 'category':
            result = 'categories'
        elif not type:
            result = type
        else:
            result = type + 's'
    else:
        result = type
    if result:
        result += ' '
    strings = ['"%s"' % s for s in strings]
    if len(strings) < 2:
        result += strings[0]
    elif len(strings) < 4:
        result += ', '.join(strings[:-1])
        result += ' and %s' % strings[-1]
    else:
        result += ', '.join(strings[:3])
        result += ' and %s more' % (len(strings) - 3)
    return result


script_ranges = {}
script_regexes = {}
for line in open('Scripts.txt'):
    line = line.strip()
    if line.startswith('#') or not line:
        continue
    parts = line.split(';', 2)
    range_str = parts[0].strip()
    script = parts[1].split()[0]
    if '..' in range_str:
        range = tuple(int(a, 16) for a in range_str.split('..'))
    else:
        range = (int(range_str, 16), int(range_str, 16))
    script_ranges.setdefault(script, []).append(range)


def is_in_script(text, scripts):
    regex = ''
    for script in scripts:
        script_regex = script_regexes.get(script, '')
        if not script_regex:
            for range in script_ranges[script]:
                if range[0] == range[1]:
                    script_regex += '%s' % (re.escape(unichr(range[0])),)
                else:
                    script_regex += '%s-%s' % tuple(map(re.escape, map(unichr, range)))
            script_regexes[script] = script_regex
        regex += script_regex
    regex = '^[%s]+$' % regex
    print regex
    return bool(re.match(regex, text))


def contains_text_in_script(text, scripts):
    regex = ''
    for script in scripts:
        for range in script_ranges[script]:
            if range[0] == range[1]:
                regex += '%s' % (re.escape(unichr(range[0])),)
            else:
                regex += '%s-%s' % tuple(map(re.escape, map(unichr, range)))
    regex = '[%s]+' % regex
    return bool(re.search(regex, text))


def mw_remove_markup(text):
    result = []
    in_template = 0
    in_comment = 0
    for token in re.split(r'(\{\{|\}\}|<!--|-->)', text):
        if token == '{{':
            in_template += 1
        elif token == '}}':
            in_template -= 1
        elif token == '<!--':
            in_comment += 1
        elif token == '-->':
            in_comment -= 1
        elif not in_template and not in_comment:
            result.append(token)
    return ''.join(result)


def out(*args):
    args = [unicode(a).encode(locale.getpreferredencoding()) for a in args]
    sys.stdout.write(' '.join(args) + '\n')
    sys.stdout.flush()

