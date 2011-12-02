import re


def mangle_name(s):
    s = s.lower()
    return re.sub(r'\W', '', s, flags=re.UNICODE)


def join_names(type, strings):
    result = type
    if len(strings) > 1:
        result += 's'
    result += ' '
    strings = ['"%s"' % s for s in strings]
    if len(strings) < 2:
        result += strings[0]
    elif len(strings) < 5:
        result += ', '.join(strings[:-1])
        result += ' and %s' % strings[-1]
    else:
        result += ', '.join(strings[:4])
        result += ' and %s more' % (len(strings) - 4)
    return result

