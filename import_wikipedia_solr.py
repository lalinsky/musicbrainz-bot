import sys
import solr

s = solr.SolrConnection('http://localhost:8983/solr/wikipedia')
for line in open(sys.argv[1]):
    line = line.rstrip('\r\n').decode('utf8').replace('_', ' ')
    s.add(id=line, name=line)
s.commit()

