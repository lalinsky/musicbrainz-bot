import mechanize
import urllib


class MusicBrainzClient(object):

    def __init__(self, username, password, server="http://musicbrainz.org"):
        self.server = server
        self.b = mechanize.Browser()
        self.b.set_handle_robots(False)
        self.b.set_debug_redirects(False)
        self.b.set_debug_http(False)
        self.b.addheaders = [('User-agent', 'musicbrainz-bot')]
        self.login(username, password)

    def url(self, path, **kwargs):
        query = ''
        if kwargs:
            query = '?' + urllib.urlencode([(k, v.encode('utf8')) for (k, v) in kwargs.items()])
        return self.server + path + query

    def login(self, username, password):
        self.b.open(self.url("/login"))
        self.b.select_form(predicate=lambda f: f.method == "POST" and "/login" in f.action)
        self.b["username"] = username
        self.b["password"] = password
        self.b.submit()
        resp = self.b.response()
        if resp.geturl() != self.url("/user/" + username):
            raise Exception('unable to login')

    def add_url(self, entity_type, entity_id, link_type_id, url, edit_note, auto=False):
        self.b.open(self.url("/edit/relationship/create_url", entity=entity_id, type=entity_type))
        self.b.select_form(predicate=lambda f: f.method == "POST" and "create_url" in f.action)
        self.b["ar.link_type_id"] = [str(link_type_id)]
        self.b["ar.url"] = str(url)
        self.b["ar.edit_note"] = edit_note.encode('utf8')
        try: self.b["ar.as_auto_editor"] = ["1"] if auto else []
        except mechanize.ControlNotFoundError: pass
        self.b.submit()
        page = self.b.response().read()
        if "Thank you, your edit has been" not in page:
            if "already exists" not in page:
                raise Exception('unable to post edit')

    def edit_artist(self, artist, update, edit_note, auto=False):
        self.b.open(self.url("/artist/%s/edit" % (artist['gid'],)))
        self.b.select_form(predicate=lambda f: f.method == "POST" and "/edit" in f.action)
        if 'country' in update:
            if self.b["edit-artist.country_id"] != ['']:
                print " * country already set, not changing"
                return
            self.b["edit-artist.country_id"] = [str(artist['country'])]
        if 'type' in update:
            if self.b["edit-artist.type_id"] != ['']:
                print " * type already set, not changing"
                return
            self.b["edit-artist.type_id"] = [str(artist['type'])]
        if 'gender' in update:
            if self.b["edit-artist.gender_id"] != ['']:
                print " * gender already set, not changing"
                return
            self.b["edit-artist.gender_id"] = [str(artist['gender'])]
        if 'begin_date' in update:
            if self.b["edit-artist.begin_date.year"]:
                print " * begin date year already set, not changing"
                return
            self.b["edit-artist.begin_date.year"] = str(artist['begin_date_year'])
            if artist['begin_date_month']:
                self.b["edit-artist.begin_date.month"] = str(artist['begin_date_month'])
                if artist['begin_date_day']:
                    self.b["edit-artist.begin_date.day"] = str(artist['begin_date_day'])
        if 'end_date' in update:
            if self.b["edit-artist.end_date.year"]:
                print " * end date year already set, not changing"
                return
            self.b["edit-artist.end_date.year"] = str(artist['end_date_year'])
            if artist['end_date_month']:
                self.b["edit-artist.end_date.month"] = str(artist['end_date_month'])
                if artist['end_date_day']:
                    self.b["edit-artist.end_date.day"] = str(artist['end_date_day'])
        self.b["edit-artist.edit_note"] = edit_note.encode('utf8')
        try: self.b["edit-artist.as_auto_editor"] = ["1"] if auto else []
        except mechanize.ControlNotFoundError: pass
        self.b.submit()
        page = self.b.response().read()
        if "Thank you, your edit has been" not in page:
            if 'any changes to the data already present' not in page:
                raise Exception('unable to post edit')

    def set_artist_type(self, entity_id, type_id, edit_note, auto=False):
        self.b.open(self.url("/artist/%s/edit" % (entity_id,)))
        self.b.select_form(predicate=lambda f: f.method == "POST" and "/edit" in f.action)
        if self.b["edit-artist.type_id"] != ['']:
            print " * already set, not changing"
            return
        self.b["edit-artist.type_id"] = [str(type_id)]
        self.b["edit-artist.edit_note"] = edit_note.encode('utf8')
        try: self.b["edit-artist.as_auto_editor"] = ["1"] if auto else []
        except mechanize.ControlNotFoundError: pass
        self.b.submit()
        page = self.b.response().read()
        if "Thank you, your edit has been" not in page:
            if 'any changes to the data already present' not in page:
                raise Exception('unable to post edit')

    def edit_url(self, entity_id, old_url, new_url, edit_note, auto=False):
        self.b.open(self.url("/url/%s/edit" % (entity_id,)))
        self.b.select_form(predicate=lambda f: f.method == "POST" and "/edit" in f.action)
        if self.b["edit-url.url"] != str(old_url):
            print " * value has changed, aborting"
            return
        if self.b["edit-url.url"] == str(new_url):
            print " * already set, not changing"
            return
        self.b["edit-url.url"] = str(new_url)
        self.b["edit-url.edit_note"] = edit_note.encode('utf8')
        try: self.b["edit-url.as_auto_editor"] = ["1"] if auto else []
        except mechanize.ControlNotFoundError: pass
        self.b.submit()
        page = self.b.response().read()
        if "Thank you, your edit has been" not in page:
            if "any changes to the data already present" not in page:
                raise Exception('unable to post edit')

    def edit_relationship(self, rel_id, entity0_type, entity1_type, old_link_type_id, new_link_type_id, attributes, edit_note, auto=False):
        self.b.open(self.url("/edit/relationship/edit", id=str(rel_id), type0=entity0_type, type1=entity1_type))
        self.b.select_form(predicate=lambda f: f.method == "POST" and "/edit" in f.action)
        if self.b["ar.link_type_id"] == [str(new_link_type_id)]:
            print " * already set, not changing"
            return
        if self.b["ar.link_type_id"] != [str(old_link_type_id)]:
            print " * value has changed, aborting"
            return
        self.b["ar.link_type_id"] = [str(new_link_type_id)]
        for k, v in attributes.items():
            self.b["ar.attrs."+k] = v
        self.b["ar.edit_note"] = edit_note.encode('utf8')
        try: self.b["ar.as_auto_editor"] = ["1"] if auto else []
        except mechanize.ControlNotFoundError: pass
        self.b.submit()
        page = self.b.response().read()
        if "Thank you, your edit has been" not in page:
            if "exists with these attributes" not in page:
                raise Exception('unable to post edit')

    def _edit_release_information(self, entity_id, attributes, edit_note, auto=False):
        self.b.open(self.url("/release/%s/edit" % (entity_id,)))
        self.b.select_form(predicate=lambda f: f.method == "POST" and "/edit" in f.action)
        changed = False
        for k, v in attributes.items():
            if self.b[k] != v[0]:
                print " * %s has changed, aborting" % k
                return
            if self.b[k] != v[1]:
                changed = True
                self.b[k] = v[1]
        if not changed:
            print " * already set, not changing"
            return
        self.b["barcode_confirm"] = ["1"]
        self.b.submit(name="step_editnote")
        page = self.b.response().read()
        self.b.select_form(predicate=lambda f: f.method == "POST" and "/edit" in f.action)
        try:
            self.b["edit_note"] = edit_note.encode('utf8')
        except mechanize.ControlNotFoundError:
            raise Exception('unable to post edit')
        try: self.b["as_auto_editor"] = ["1"] if auto else []
        except mechanize.ControlNotFoundError: pass
        self.b.submit(name="save")
        page = self.b.response().read()
        if "Release information" not in page:
            raise Exception('unable to post edit')

    def set_release_script(self, entity_id, old_script_id, new_script_id, edit_note, auto=False):
        self._edit_release_information(entity_id, {"script_id": [[str(old_script_id)],[str(new_script_id)]]}, edit_note, auto)
