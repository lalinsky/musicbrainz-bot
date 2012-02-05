#!/usr/bin/python

import sys
import solr

for file in sys.argv[1:]:
    lang = file[:2]
    suffix = '_' + lang if lang != 'en' else ''
    s = solr.SolrConnection('http://localhost:8983/solr/wikipedia' + suffix)
    s.delete_query('*:*')
    for line in open(sys.argv[1]):
        id = line.rstrip('\r\n').decode('utf8')
        name = id.replace('_', ' ')
        s.add(id=id, name=name)
s.commit()

