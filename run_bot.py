import logging
import configparser
import pandas
from editing import MusicBrainzClient
from selenium.webdriver.remote.remote_connection import LOGGER as SELENIUM_LOGGER

SELENIUM_LOGGER.setLevel(logging.CRITICAL)


def load_starting_data(config: configparser.ConfigParser):
    """

    Args:
        config (configparser.ConfigParser):
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


def init_mb_client(config: configparser.ConfigParser):
    mb_user = config.get("musicbrainz", "username")
    mb_pw = config.get("musicbrainz", "password")
    mb_server = config.get("musicbrainz", "server")
    headless = config.get("general", "headless")
    return MusicBrainzClient(mb_user, mb_pw, server=mb_server, headless=headless)


def main():
    # Init logging
    logging.basicConfig(encoding='utf-8', level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p',
                        handlers=[
                            logging.FileHandler("bot.log"),
                            logging.StreamHandler()
                        ]
                    )

    # Load config
    config = configparser.ConfigParser()
    config.read("config.ini")

    # Load DAHR data
    id_mappings = load_starting_data(config)

    # Init MB client
    mb_client = init_mb_client(config)
    logging.info(f"Logged in to MusicBrainz as {mb_client.username} at {mb_client.server}")
    edits_left = mb_client.edits_left()[0]
    if edits_left <= 0:
        logging.info("No more edits available for today.")
        return
    logging.info(f"Edits available for today: {edits_left}")

    # Editing loop
    for entry in id_mappings:
        logging.info(f"Checking MB entry {entry['mb']}")
        mb_client.add_external_link(entry["mb"], entry["dahr"])


if __name__ == "__main__":
    main()
