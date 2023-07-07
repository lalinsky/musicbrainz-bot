"""
Run a bot to add DAHR identifiers to MusicBrainz.
"""

import logging
import configparser
import json
import os
from pathlib import Path
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


def save_progress(config: configparser.ConfigParser, checked: list, modified: list):
    """
    Saves list of checked entries & modified entries to files specified in config.
    Args:
        config: Loaded configuration info
        checked: List of id mappings already checked
        modified: List of id mappings that we modified
    """
    checked_out = config.get("general", "checked_file")
    os.makedirs(os.path.dirname(checked_out), exist_ok=True)
    with open(checked_out, "w", encoding="utf-8") as checked_file:
        json.dump(checked, checked_file, indent=4)

    modified_out = config.get("general", "modified_file")
    os.makedirs(os.path.dirname(checked_out), exist_ok=True)
    with open(modified_out, "w", encoding="utf-8") as mod_file:
        json.dump(modified, mod_file, indent=4)

    logging.info(f"Progress saved to {checked_out} and {modified_out}")


def load_progress(config: configparser.ConfigParser) -> (list, list):
    """
    Load previously checked and modified entries from files specified in config.
    Args:
        config:  Loaded configuration info

    Returns:
        List of previously checked id mappings, and list of previously modified id mappings
    """
    checked_out = config.get("general", "checked_file")
    if os.path.isfile(checked_out):
        with open(checked_out, "r", encoding="utf-8") as checked_file:
            checked = json.load(checked_file)
        logging.info(f"Checked entries loaded from {checked_out}")

    else:
        checked = []

    modified_out = config.get("general", "modified_file")
    if os.path.isfile(modified_out):
        with open(modified_out, "r", encoding="utf-8") as mod_file:
            modified = json.load(mod_file)
        logging.info(f"Modified entries loaded from {modified_out}")

    else:
        modified = []

    return checked, modified


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
    checked, modified = load_progress(config)
    errors = []

    # Get mappings that aren't in the saved data
    unchecked_mappings = [mapping for mapping in id_mappings if mapping not in checked]
    if not unchecked_mappings:
        logging.info(
            "All entries already checked. "
            "To rerun, clear the saved data files specified in 'config.ini'", extra={"test": "noodle"}
        )
        return
    # Log number of already-checked entries
    if checked:
        logging.info(f"Already checked {len(checked)}/{len(id_mappings)} entries")

    # Init MB client
    mb_client = init_mb_client(config)
    edits_left = mb_client.edits_left()[0]
    if edits_left <= 0:
        return

    # Editing loop
    for num, entry in enumerate(unchecked_mappings):
        # If we're out of edits for the day, stop
        if edits_left <= 0:
            logging.warning("Out of edits for today. Try again later.")
            save_progress(config, checked, modified)
            break

        # Check an entry
        logging.info(f"Checking MB entry {entry['mb']}")
        try:
            link_added = mb_client.add_external_link(entry["mb"], entry["dahr"])
            checked.append(entry)
            if link_added:
                modified.append(entry)
                edits_left -= 1

        # If the edit request times out or otherwise failed, the entry wasn't fully checked.
        # Save it for the next run.
        except (TimeoutError, RuntimeError):
            errors.append(entry)

        # Save progress every 20 people
        if (num + 1) % 3 == 0:
            save_progress(config, checked, modified)

    if errors:
        logging.error(f"{len(errors)} were not checked successfully. Please run again.")
    else:
        logging.info(
            f"{len(checked)}/{len(id_mappings)} checked successfully. "
            f"{len(modified)} links added."
        )


if __name__ == "__main__":
    run()
