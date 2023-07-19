"""
Run a bot to add DAHR identifiers to MusicBrainz.
"""

import logging
import configparser
import json
import os
import pandas
from selenium.webdriver.remote.remote_connection import LOGGER as SELENIUM_LOGGER
from editing import MusicBrainzClient

SELENIUM_LOGGER.setLevel(logging.CRITICAL)


def load_starting_data(config: configparser.ConfigParser) -> list:
    """
    Load DAHR data.
    Args:
        config (configparser.ConfigParser): Loaded configuration info

    Returns:
        List of dicts mapping DAHR IDs (key "dahr") to MusicBrainz IDs (key "mb")
    """

    # Load DAHR data
    input_file = config.get("dahr", "input_csv")
    dahr_field = config.get("dahr", "dahr_id_field")
    mb_field = config.get("dahr", "mb_id_field")
    dahr_entries = pandas.read_csv(input_file)
    dahr_entries = dahr_entries.rename(columns={dahr_field: "dahr", mb_field: "mb"})

    id_mappings = dahr_entries[dahr_entries["mb"].notna()]
    id_mappings = id_mappings[["mb", "dahr"]]
    id_mappings["mb"] = id_mappings["mb"].apply(
        lambda x: x if "musicbrainz.org" not in x else x.split("/")[-1]
    )
    id_mappings["dahr"] = id_mappings["dahr"].apply(
        lambda x: f"https://adp.library.ucsb.edu/names/{x}"
    )
    return id_mappings.to_dict("records")


def init_mb_client(config: configparser.ConfigParser) -> MusicBrainzClient:
    """
    Initalize a MusicBrainzClient, which includes starting Selenium and logging in to MusicBrainz.

    Args:
        config: Loaded configuration info

    Returns:
        MusicBrainzClient, signed in with the information specified in config.
    """
    mb_user = config.get("musicbrainz", "username")
    mb_pw = config.get("musicbrainz", "password")
    mb_server = config.get("musicbrainz", "server")
    headless = config.get("general", "headless") == "True"
    return MusicBrainzClient(mb_user, mb_pw, server=mb_server, headless=headless)


def save_progress(
    config: configparser.ConfigParser, checked: list, modified: list, errors: list
):
    """
    Saves list of checked entries & modified entries to files specified in config.
    Args:
        config: Loaded configuration info
        checked: List of id mappings already checked
        modified: List of id mappings that we modified
        errors: List of id mappings that produced an error
    """
    checked_out = config.get("general", "checked_file")
    os.makedirs(os.path.dirname(checked_out), exist_ok=True)
    with open(checked_out, "w", encoding="utf-8") as checked_file:
        json.dump(checked, checked_file, indent=4)

    modified_out = config.get("general", "modified_file")
    os.makedirs(os.path.dirname(checked_out), exist_ok=True)
    with open(modified_out, "w", encoding="utf-8") as mod_file:
        json.dump(modified, mod_file, indent=4)

    error_out = config.get("general", "error_file")
    os.makedirs(os.path.dirname(error_out), exist_ok=True)
    with open(error_out, "w", encoding="utf-8") as error_file:
        json.dump(errors, error_file, indent=4)

    logging.info("Progress saved to %s & %s & %s", checked_out, modified_out, error_out)


def load_progress(config: configparser.ConfigParser) -> (list, list, list):
    """
    Load previously checked and modified entries from files specified in config.
    Args:
        config:  Loaded configuration info

    Returns:
        Lists of previous: checked id mappings, modified id mappings, and errors
    """
    # Load Checked
    checked_out = config.get("general", "checked_file")
    if os.path.isfile(checked_out):
        with open(checked_out, "r", encoding="utf-8") as checked_file:
            checked = json.load(checked_file)
        logging.info("Checked entries loaded from %s", checked_out)

    else:
        checked = []

    # Load modified
    modified_out = config.get("general", "modified_file")
    if os.path.isfile(modified_out):
        with open(modified_out, "r", encoding="utf-8") as mod_file:
            modified = json.load(mod_file)
        logging.info("Modified entries loaded from %s", modified_out)

    else:
        modified = []

    # Load errors
    error_out = config.get("general", "error_file")
    if os.path.isfile(error_out):
        with open(error_out, "r", encoding="utf-8") as error_file:
            errors = json.load(error_file)
        logging.info("Error loaded from %s", error_out)

    else:
        errors = []

    return checked, modified, errors


def run():
    """
    Main method for bot.
    """

    # Load config
    config = configparser.ConfigParser()
    config.read("config.ini")

    # Init logging
    log_file = config.get("general", "log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        encoding="utf-8",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s ",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )

    # Load DAHR data
    id_mappings = load_starting_data(config)

    # Check for existing saved data
    checked, modified, errors = load_progress(config)

    # Get mappings that aren't in the saved data
    unchecked_mappings = [mapping for mapping in id_mappings if mapping not in checked]
    if not unchecked_mappings:
        logging.info(
            "All entries already checked. "
            "To rerun, clear the saved data files specified in 'config.ini'"
        )
        return
    # Log number of already-checked entries
    if checked:
        logging.info("Already checked %s/%s entries", len(checked), len(id_mappings))

    # Init MB client
    mb_client = init_mb_client(config)
    edits_left = mb_client.edits_left()
    if edits_left <= 0:
        return

    # Editing loop
    for num, entry in enumerate(unchecked_mappings):
        # If we're out of edits for the day, stop
        if edits_left <= 0:
            logging.warning("Out of edits for today. Try again later.")
            save_progress(config, checked, modified, errors)
            break

        # Check an entry
        logging.info("Checking MB entry %s", entry["mb"])
        try:
            link_added = mb_client.add_external_link(
                entry["mb"], entry["dahr"], edit_note=config.get("general", "edit_note")
            )
            checked.append(entry)
            if link_added:
                modified.append(entry)
                edits_left -= 1

        # If the edit request times out or otherwise failed, the entry wasn't fully checked.
        # Save it for the next run.
        except (TimeoutError, RuntimeError):
            errors.append(entry)

        # Save progress every N people
        save_interval = int(config.get("general", "save_interval"))
        if (num + 1) % save_interval == 0:
            save_progress(config, checked, modified, errors)

    if errors:
        logging.error(
            "%s were not checked successfully. Please run again.", len(errors)
        )
    else:
        logging.info(
            "%s/%s checked successfully. %s links added.",
            len(checked),
            len(id_mappings),
            len(modified),
        )


if __name__ == "__main__":
    run()
