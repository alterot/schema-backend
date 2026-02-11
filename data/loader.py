"""
Data loader for realistic hospital data.
Loads and provides access to personnel, staffing requirements, and rules.
"""

import json
import os
from typing import Dict, List, Any, Optional
from datetime import date
from functools import lru_cache
import holidays

# Path to the data file
DATA_FILE = os.path.join(os.path.dirname(__file__), 'realistic_hospital_data.json')


@lru_cache(maxsize=1)
def load_realistic_data() -> Dict[str, Any]:
    """
    Laddar JSON-filen med sjukhusdata.
    Cachad för att undvika upprepade filläsningar.

    Returns:
        Dict med all data från realistic_hospital_data.json
    """
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_personal() -> List[Dict[str, Any]]:
    """
    Returnerar listan med personal i format som passar API:et.

    Returns:
        Lista med personal-dicts i API-format:
        {
            "namn": str,
            "roll": str,
            "anstallning": int,
            "tillganglighet": List[str],
            "franvaro": List[Dict]
        }
    """
    data = load_realistic_data()
    personal_list = []

    for person in data['personal']:
        personal_list.append({
            'namn': person['namn'],
            'roll': person['roll'],
            'anstallning': person['anstallning'],
            'tillganglighet': person['tillganglighet'],
            'franvaro': person.get('franvaro', [])
        })

    return personal_list


def get_bemanningsbehov(is_weekend: bool = False) -> Dict[str, Dict[str, int]]:
    """
    Returnerar bemanningsbehov for vardag eller helg.

    Args:
        is_weekend: True for helgbehov, False for vardagbehov

    Returns:
        Dict med behov per passtyp:
        {
            "dag": {"lakare": 1, "sjukskoterska": 3, "underskoterska": 5},
            "kvall": {...},
            "natt": {...}
        }
    """
    data = load_realistic_data()
    behov_typ = 'helg' if is_weekend else 'vardag'
    return data['bemanningsbehov'][behov_typ]


def get_regler() -> Dict[str, Any]:
    """
    Returnerar regler-objektet.

    Returns:
        Dict med regler:
        {
            "vilotid_timmar": 11,
            "max_dagar_i_rad": 5,
            "max_timmar_per_vecka_heltid": 40,
            "overtid_faktor": 1.5,
            "timloner": {"lakare": 650, ...}
        }
    """
    data = load_realistic_data()
    return data['regler']


def get_avdelning() -> Dict[str, Any]:
    """
    Returnerar avdelningsinformation.

    Returns:
        Dict med avdelningsdata
    """
    data = load_realistic_data()
    return data['avdelning']


def generate_shifts_for_period(
    start_date: date,
    end_date: date,
    avdelning: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Genererar shift-behov for en given period baserat pa bemanningsbehov.

    Args:
        start_date: Startdatum
        end_date: Slutdatum
        avdelning: Avdelningsnamn (default fran data)

    Returns:
        Lista med shift-dicts i API-format (behov)
    """
    data = load_realistic_data()

    if avdelning is None:
        avdelning = data['avdelning']['namn']

    shifts = []
    current_date = start_date

    se_holidays = holidays.SE(years=[start_date.year, end_date.year])

    while current_date <= end_date:
        is_weekend = current_date.weekday() >= 5 or current_date in se_holidays
        behov = get_bemanningsbehov(is_weekend)

        for pass_typ in ['dag', 'kvall', 'natt']:
            # Mappa passtyp till API-format
            pass_namn = pass_typ if pass_typ != 'kvall' else 'kväll'

            shifts.append({
                'datum': current_date.isoformat(),
                'pass': pass_namn,
                'avdelning': avdelning,
                'kompetenskrav': behov[pass_typ]
            })

        # Ga till nasta dag
        from datetime import timedelta
        current_date = current_date + timedelta(days=1)

    return shifts


def get_scenario(scenario_name: str) -> Optional[Dict[str, Any]]:
    """
    Hamtar ett specifikt testscenario.

    Args:
        scenario_name: Namn pa scenariot (t.ex. "normal_april", "hog_franvaro")

    Returns:
        Scenario-dict eller None om det inte finns
    """
    data = load_realistic_data()
    return data.get('scenarios', {}).get(scenario_name)


def clear_cache():
    """Rensar cachen for load_realistic_data (anvandbart vid test)."""
    load_realistic_data.cache_clear()
