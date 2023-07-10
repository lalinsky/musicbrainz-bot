import logging
import urllib
import re
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.firefox.options import Options
from selenium.common.exceptions import TimeoutException


class MusicBrainzClient(object):
    def __init__(self, username, password, server="https://test.musicbrainz.org", headless=False):
        self.server = server
        self.username = username

        ff_options = Options()
        if headless:
            ff_options.headless = headless
        self.b = webdriver.Firefox(options=ff_options)
        self.login(username, password)

    def url(self, path, **kwargs):
        query = ""
        if kwargs:
            query = "?" + urllib.parse.urlencode(
                [(k, v.encode("utf8")) for (k, v) in kwargs.items()]
            )
        return self.server + path + query

    def login(self, username, password):
        login_url = self.url("/login")
        self.b.get(login_url)
        username_field = self.b.find_element(By.ID, "id-username")
        username_field.clear()
        username_field.send_keys(username)

        pw_field = self.b.find_element(By.ID, "id-password")
        pw_field.clear()
        pw_field.send_keys(password)
        pw_field.send_keys(Keys.RETURN)

        WebDriverWait(self.b, 15).until(EC.url_changes(login_url))

        if self.b.current_url != self.url("/user/" + username):
            raise Exception("Unable to login. Is your password correct?")

        logging.info(f"Logged in to MusicBrainz as {self.username} at {self.server}")

    # return tuple (normal_edits_left, edits_left)
    # TODO: This could be more efficient if it used the table on the user page. Fewer page loads.
    def edits_left(self, max_open_edits=2000, max_edits_per_day=1000):

        # Check num of edits made today
        re_found_edits = re.compile(r"Found (?:at least )?([0-9]+(?:,[0-9]+)?) edits?")
        kwargs = {
            "page": "2000",
            "combinator": "and",
            "conditions.0.field": "open_time",
            "conditions.0.operator": ">",
            "conditions.0.args.0": "today",
            "conditions.0.args.1": "",
            "conditions.1.field": "editor",
            "conditions.1.operator": "me",
        }
        url = self.url("/search/edits", **kwargs)
        self.b.get(url)
        page = self.b.page_source
        match = re_found_edits.search(page)
        if not match:
            logging.error("Could not determine remaining daily edits")
            return 0, 0
        edits_today = int(re.sub(r"[^0-9]+", "", match.group(1)))
        edits_left = max_edits_per_day - edits_today
        if edits_left <= 0:
            logging.info("No more edits available for today. Try again tomorrow.")
            return 0, 0

        # Check number of open edits
        url = self.url("/user/%s/edits/open" % (self.username,), page="2000")
        self.b.get(url)
        page = self.b.page_source
        match = re_found_edits.search(page)
        if not match:
            logging.error("Could not determine open edits")
            return 0, 0
        open_edits = int(re.sub(r"[^0-9]+", "", match.group(1)))
        normal_edits_left = min(edits_left, max_open_edits - open_edits)
        logging.info(f"Edits available for today: {edits_left}")
        return normal_edits_left, edits_left

    def add_external_link(self, artist_id, link, edit_note=None, force_votable=True):
        # get artist edit page
        artist_url = self.url(f"/artist/{artist_id}")
        artist_edit_url = f"{artist_url}/edit"
        self.b.get(artist_edit_url)
        if self.b.current_url != artist_edit_url and "/artist/" in self.b.current_url:
            # Artist ID redirected
            artist_url = self.b.current_url.replace("/edit", "")

        # wait for JS to load external links table
        WebDriverWait(self.b, 15).until(
            EC.presence_of_element_located((By.ID, "external-links-editor"))
        )

        # check if artist has DAHR link already
        page = self.b.page_source
        re_found_dahr_link = re.compile(r"adp.library.ucsb.edu/names")
        dahr_link_found = re_found_dahr_link.search(page)
        if dahr_link_found:
            logging.info(f"\tDAHR link already present for MB id {artist_id}")
            return False

        # Add URL
        url_input = self.b.find_element(
            By.XPATH, "//input[@placeholder='Add another link']"
        )
        url_input.clear()
        url_input.send_keys(link)

        # Add edit note
        if edit_note:
            self.b.find_element(By.ID, "id-edit-artist.edit_note").send_keys(edit_note)

        # Make edit votable
        if force_votable:
            self.b.find_element(By.ID, "id-edit-artist.make_votable").click()

        # Submit edit
        self.b.find_element(By.CSS_SELECTOR, "button.submit").click()

        try:
            # wait for edit to go through
            WebDriverWait(self.b, 60).until(EC.url_changes(artist_edit_url))
        except TimeoutException:
            logging.error(f"\tEdit timed out for MB entry {artist_id}")
            raise TimeoutError

        # If we don't end up back on the artist page, something went weird with the edit
        if self.b.current_url != artist_url:
            raise RuntimeError(f"\tEdit failed for MB entry {artist_id}")

        # If we get here, the edit was made successfully
        logging.info(f"\tAdded link to MB entry {artist_id}")
        return True

    def __del__(self):
        # Close selenium when object is removed
        self.b.close()
