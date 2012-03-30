# -*- coding: utf-8 -*-
import re
import sys
import locale
from editing import MusicBrainzClient
from mbbot.utils.pidfile import PIDFile
from utils import out
import config as cfg

def main(args):
    if not args:
        out('Usage:   cancel_edits.py <edit_number edit_note>...\n')
        out('Example: cancel_edits.py "Edit #123 my mistake"')
        out('         cancel_edits.py 123 124 125')
        return

    edits = []
    for arg in args:
        if not isinstance(arg, unicode):
            arg = unicode(arg, locale.getpreferredencoding())
        m = re.match(ur'(?:[Ee]dit )?#?([0-9]+) ?(.*)$', arg)
        if not m:
            out('invalid edit number "%s", aborting!' % arg)
            return
        edit_nr = str(m.group(1))
        edit_note = m.group(2).lstrip()
        edits.append((edit_nr, edit_note))

    mb = MusicBrainzClient(cfg.MB_USERNAME, cfg.MB_PASSWORD, cfg.MB_SITE)
    for edit_nr, edit_note in edits:
        out(u'Cancel edit #%s: %s' % (edit_nr, edit_note if edit_note else u'<no edit note>'))
        mb.cancel_edit(str(edit_nr), edit_note)

if __name__ == '__main__':
    with PIDFile('/tmp/mbbot_cancel_edits.pid'):
        main(sys.argv[1:])
