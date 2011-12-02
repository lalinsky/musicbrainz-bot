# MusicBrainz Bot

This bot it indended to add various data from the internet to MusicBrainz. For now, it only adds Wikipedia links to artists, but it should be extended to do more work.

## Wikipedia Artist Links

It goes over all artists that do not have a Wikipedia link yet, and searches for the name in a local Solr index of English Wikipedia article titles. Once it finds a match,
it will fetch the article text from Wikipedia's API and verify that the text contains at least some release or release group titles (self-titled albums are ignored).

