import requests
import logging
from pprint import pprint
# The arrow library is used to handle datetimes
import arrow

PRODUCTION_URL = "https://www.hydroquebec.com/data/documents-donnees/donnees-ouvertes/json/production.json"
CONSUMPTION_URL = "https://www.hydroquebec.com/data/documents-donnees/donnees-ouvertes/json/demande.json"
# Reluctant to call it 'timezone', since we are importing 'timezone' from datetime
timezone_id = 'America/Montreal'

def fetch_production(
    zone_key="CA-QC",
    session=None,
    target_datetime=None,
    logger=logging.getLogger(__name__),
) -> dict:
    """Requests the last known production mix (in MW) of a given region.
       In this particular case, translated mapping of JSON keys are also required"""

    def if_exists(elem: dict, etype: str):

        english = {
            "hydraulique": "hydro",
            "thermique": "thermal",
            "solaire": "solar",
            "eolien": "wind",
            "autres": "unknown",
            "valeurs": "values",
        }
        english = {v: k for k, v in english.items()}
        try:
            return elem["valeurs"][english[etype]]
        except KeyError:
            return 0.0

    data = _fetch_quebec_production()
    for elem in reversed(data["details"]):
        if elem["valeurs"]["total"] != 0:

            return {
                "zoneKey": zone_key,
                "datetime":  arrow.get(elem["date"], tzinfo=timezone_id).datetime,
                "production": {
                    "biomass": 0.0,
                    "coal": 0.0,
                    "gas": 0.0,
                    "hydro": if_exists(elem, "hydro"),
                    "nuclear": 0.0,
                    "oil": 0.0,
                    "solar": if_exists(elem, "solar"),
                    "wind": if_exists(elem, "wind"),
                    "geothermal": if_exists(elem, "geothermal"),
                    "unknown": if_exists(elem, "unknown"),
                },
                "source": "hydroquebec.com",
            }


def fetch_consumption(zone_key="CA-QC", session=None, target_datetime=None, logger=None):
    data = _fetch_quebec_consumption()
    for elem in reversed(data["details"]):
        if "demandeTotal" in elem["valeurs"]:
            return {
                "zoneKey": zone_key,
                "datetime": arrow.get(elem["date"], tzinfo=timezone_id).datetime,
                "consumption": elem["valeurs"]["demandeTotal"],
                "source": "hydroquebec.com",
            }


def _fetch_quebec_production(logger=logging.getLogger(__name__)) -> str:
    response = requests.get(PRODUCTION_URL)

    if not response.ok:
        logger.info('CA-QC: failed getting requested production data from hydroquebec - URL {}'.format(PRODUCTION_URL))
    return response.json()


def _fetch_quebec_consumption(logger=logging.getLogger(__name__)) -> str:
    response = requests.get(CONSUMPTION_URL)

    if not response.ok:
        logger.info('CA-QC: failed getting requested consumption data from hydroquebec - URL {}'.format(CONSUMPTION_URL))
    return response.json()


if __name__ == '__main__':
    """Main method, never used by the Electricity Map backend, but handy for testing."""

    test_logger = logging.getLogger()

    print('fetch_production() ->')
    pprint(fetch_production(logger=test_logger))

    print('fetch_consumption() ->')
    pprint(fetch_consumption(logger=test_logger))
