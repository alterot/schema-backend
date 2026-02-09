from typing import Dict, List, Any
from datetime import date


class ValidationError(Exception):
    """Custom exception för valideringsfel"""
    pass


def validate_input(data: Dict[str, Any]) -> None:
    """
    Validerar input-data från API-anrop.
    Kastar ValidationError om data är ogiltig.
    """
    # Validera att alla required fields finns
    required_fields = ['personal', 'behov', 'config']
    for field in required_fields:
        if field not in data:
            raise ValidationError(f"Saknar obligatoriskt fält: '{field}'")

    # Validera personal
    if not isinstance(data['personal'], list) or len(data['personal']) == 0:
        raise ValidationError("'personal' måste vara en lista med minst en person")

    for idx, person in enumerate(data['personal']):
        validate_person(person, idx)

    # Validera behov
    if not isinstance(data['behov'], list) or len(data['behov']) == 0:
        raise ValidationError("'behov' måste vara en lista med minst ett pass")

    for idx, shift in enumerate(data['behov']):
        validate_shift(shift, idx)

    # Validera config
    validate_config(data['config'])


def validate_person(person: Dict, idx: int) -> None:
    """Validerar en person-dict"""
    required = ['namn', 'roll', 'anstallning', 'tillganglighet']
    for field in required:
        if field not in person:
            raise ValidationError(
                f"Person {idx}: Saknar obligatoriskt fält '{field}'"
            )

    # Validera anställningsgrad
    if not isinstance(person['anstallning'], (int, float)):
        raise ValidationError(
            f"Person {idx} ({person.get('namn', 'okänd')}): "
            f"'anstallning' måste vara ett nummer"
        )

    if not 0 < person['anstallning'] <= 100:
        raise ValidationError(
            f"Person {idx} ({person.get('namn', 'okänd')}): "
            f"'anstallning' måste vara mellan 1 och 100%"
        )

    # Validera tillgänglighet
    if not isinstance(person['tillganglighet'], list):
        raise ValidationError(
            f"Person {idx} ({person.get('namn', 'okänd')}): "
            f"'tillganglighet' måste vara en lista"
        )

    giltiga_dagar = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for dag in person['tillganglighet']:
        if dag not in giltiga_dagar:
            raise ValidationError(
                f"Person {idx} ({person.get('namn', 'okänd')}): "
                f"Ogiltig veckodag '{dag}'. Använd: {', '.join(giltiga_dagar)}"
            )

    # Validera frånvaro (om den finns)
    if 'franvaro' in person:
        if not isinstance(person['franvaro'], list):
            raise ValidationError(
                f"Person {idx} ({person.get('namn', 'okänd')}): "
                f"'franvaro' måste vara en lista"
            )

        for f_idx, franvaro in enumerate(person['franvaro']):
            validate_franvaro(franvaro, person.get('namn', 'okänd'), f_idx)


def validate_franvaro(franvaro: Dict, person_namn: str, idx: int) -> None:
    """Validerar en frånvaro-dict"""
    required = ['start', 'slut']
    for field in required:
        if field not in franvaro:
            raise ValidationError(
                f"Person {person_namn}, frånvaro {idx}: "
                f"Saknar obligatoriskt fält '{field}'"
            )

    # Validera datumformat
    try:
        start = date.fromisoformat(franvaro['start'])
        slut = date.fromisoformat(franvaro['slut'])
    except (ValueError, TypeError):
        raise ValidationError(
            f"Person {person_namn}, frånvaro {idx}: "
            f"Ogiltigt datumformat. Använd ISO-format (YYYY-MM-DD)"
        )

    # Validera att slut >= start
    if slut < start:
        raise ValidationError(
            f"Person {person_namn}, frånvaro {idx}: "
            f"Slutdatum ({slut}) kan inte vara före startdatum ({start})"
        )


def validate_shift(shift: Dict, idx: int) -> None:
    """Validerar ett pass-dict"""
    required = ['datum', 'pass', 'avdelning', 'kompetenskrav']
    for field in required:
        if field not in shift:
            raise ValidationError(
                f"Pass {idx}: Saknar obligatoriskt fält '{field}'"
            )

    # Validera datum
    try:
        date.fromisoformat(shift['datum'])
    except (ValueError, TypeError):
        raise ValidationError(
            f"Pass {idx}: Ogiltigt datumformat för '{shift['datum']}'. "
            f"Använd ISO-format (YYYY-MM-DD)"
        )

    # Validera passtyp
    giltiga_pass = ['dag', 'kväll', 'natt']
    if shift['pass'] not in giltiga_pass:
        raise ValidationError(
            f"Pass {idx}: Ogiltig passtyp '{shift['pass']}'. "
            f"Använd: {', '.join(giltiga_pass)}"
        )

    # Validera kompetenskrav
    if not isinstance(shift['kompetenskrav'], dict):
        raise ValidationError(
            f"Pass {idx}: 'kompetenskrav' måste vara ett objekt"
        )

    if len(shift['kompetenskrav']) == 0:
        raise ValidationError(
            f"Pass {idx}: 'kompetenskrav' måste innehålla minst en roll"
        )

    for roll, antal in shift['kompetenskrav'].items():
        if not isinstance(antal, int) or antal < 0:
            raise ValidationError(
                f"Pass {idx}: Kompetenskrav för '{roll}' måste vara ett positivt heltal"
            )


def validate_config(config: Dict) -> None:
    """Validerar config-dict"""
    if 'period' not in config:
        raise ValidationError("Config saknar obligatoriskt fält 'period'")

    # Validera periodformat (t.ex. "2025-04")
    try:
        year, month = config['period'].split('-')
        year = int(year)
        month = int(month)
        if not (1 <= month <= 12):
            raise ValueError()
    except (ValueError, AttributeError):
        raise ValidationError(
            f"Config: Ogiltigt periodformat '{config['period']}'. "
            f"Använd format YYYY-MM (t.ex. '2025-04')"
        )
