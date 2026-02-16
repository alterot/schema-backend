"""
Modul för att beräkna metrics för scheman.
Används för att mäta kvalitet, kostnad och effektivitet.
"""

from typing import List, Dict, Tuple
from collections import defaultdict


# Konstanter för lönekostnader (kr per timme)
HOURLY_RATE_SSK = 350  # Sjuksköterska
HOURLY_RATE_USK = 280  # Undersköterska
OVERTIME_MULTIPLIER = 1.5  # Övertidsersättning är 150%
HOURS_PER_SHIFT = 8  # Varje pass är 8 timmar


def calculate_coverage_percent(schema_rader: List, shifts: List) -> float:
    """
    Beräknar andel bemannade pass av totalt antal behov.

    Args:
        schema_rader: Lista med SchemaRad-objekt (från Schedule.rader)
        shifts: Lista med Shift-objekt (alla pass som ska bemannas)

    Returns:
        Coverage i procent (0.0 - 100.0)
    """
    if not shifts:
        return 100.0

    # Räkna pass som har minst en person
    bemannade_pass = sum(1 for rad in schema_rader if len(rad.personal) > 0)
    totalt_antal_pass = len(shifts)

    return round((bemannade_pass / totalt_antal_pass) * 100, 1)


def calculate_overtime_hours(schema_rader: List, personal: List) -> float:
    """
    Beräknar total övertid (timmar över anställningsgrad).

    Args:
        schema_rader: Lista med SchemaRad-objekt
        personal: Lista med Person-objekt

    Returns:
        Total övertid i timmar
    """
    # Räkna pass per person
    pass_per_person = defaultdict(int)
    for rad in schema_rader:
        for person_namn in rad.personal:
            pass_per_person[person_namn] += 1

    # Skapa lookup för max pass per person
    max_pass_lookup = {p.namn: p.max_arbetspass_per_manad for p in personal}

    # Beräkna övertid
    total_overtime_hours = 0.0
    for person_namn, antal_pass in pass_per_person.items():
        max_pass = max_pass_lookup.get(person_namn, antal_pass)  # Fallback om person saknas
        overtime_pass = max(0, antal_pass - max_pass)
        total_overtime_hours += overtime_pass * HOURS_PER_SHIFT

    return round(total_overtime_hours, 1)


def calculate_rule_violations(konflikter: List) -> int:
    """
    Räknar antal faktiska regelbrott (allvarlighetsgrad >= 1).
    Överbemanning (allvarlighetsgrad 0) är info, inte ett regelbrott.

    Args:
        konflikter: Lista med Konflikt-objekt

    Returns:
        Antal regelbrott
    """
    return sum(
        1 for k in konflikter
        if (k.allvarlighetsgrad if hasattr(k, 'allvarlighetsgrad') else k.get('allvarlighetsgrad', 1)) >= 1
    )


def calculate_cost_kr(schema_rader: List, personal: List) -> float:
    """
    Beräknar total lönekostnad inklusive övertidsersättning.

    Args:
        schema_rader: Lista med SchemaRad-objekt
        personal: Lista med Person-objekt

    Returns:
        Total kostnad i kronor
    """
    # Skapa lookup för person -> roll
    person_roll_lookup = {p.namn: p.roll for p in personal}
    max_pass_lookup = {p.namn: p.max_arbetspass_per_manad for p in personal}

    # Räkna pass per person
    pass_per_person = defaultdict(int)
    for rad in schema_rader:
        for person_namn in rad.personal:
            pass_per_person[person_namn] += 1

    total_cost = 0.0

    for person_namn, antal_pass in pass_per_person.items():
        roll = person_roll_lookup.get(person_namn, "underskoterska")  # Default till USK
        max_pass = max_pass_lookup.get(person_namn, antal_pass)

        # Bestäm timpris baserat på roll
        if "sjuksköterska" in roll.lower() or "ssk" in roll.lower():
            hourly_rate = HOURLY_RATE_SSK
        else:
            hourly_rate = HOURLY_RATE_USK

        # Normala pass
        normal_pass = min(antal_pass, max_pass)
        normal_hours = normal_pass * HOURS_PER_SHIFT
        normal_cost = normal_hours * hourly_rate

        # Övertidspass
        overtime_pass = max(0, antal_pass - max_pass)
        overtime_hours = overtime_pass * HOURS_PER_SHIFT
        overtime_cost = overtime_hours * hourly_rate * OVERTIME_MULTIPLIER

        total_cost += normal_cost + overtime_cost

    return round(total_cost, 2)


def calculate_quality_score(
    coverage_percent: float,
    rule_violations: int,
    overtime_hours: float,
    total_shifts: int
) -> int:
    """
    Beräknar sammanvägd kvalitetspoäng (0-100).

    Viktning:
    - Coverage: 40% (högre är bättre)
    - Rule violations: 30% (färre är bättre)
    - Overtime: 20% (mindre är bättre)
    - Efficiency: 10% (baserat på totalt antal pass)

    Args:
        coverage_percent: Coverage i procent (0-100)
        rule_violations: Antal regelbrott
        overtime_hours: Total övertid i timmar
        total_shifts: Totalt antal pass i schemat

    Returns:
        Quality score (0-100)
    """
    # Coverage-poäng (0-40)
    coverage_score = (coverage_percent / 100) * 40

    # Violations-poäng (0-30)
    # Max 10 violations innan poängen blir 0
    violation_penalty = min(rule_violations * 3, 30)
    violations_score = 30 - violation_penalty

    # Övertids-poäng (0-20)
    # Idealisk övertid = 0%, > 10% av totala timmar = 0 poäng
    if total_shifts == 0:
        overtime_score = 20
    else:
        total_hours = total_shifts * HOURS_PER_SHIFT
        overtime_percent = (overtime_hours / total_hours) * 100
        overtime_penalty = min(overtime_percent * 2, 20)
        overtime_score = 20 - overtime_penalty

    # Efficiency-poäng (0-10)
    # Ger full poäng om schemat är komplett
    efficiency_score = 10 if coverage_percent >= 95 else (coverage_percent / 95) * 10

    # Summera och avrunda
    total_score = coverage_score + violations_score + overtime_score + efficiency_score

    return round(max(0, min(100, total_score)))


def calculate_all_metrics(
    schema_rader: List,
    konflikter: List,
    shifts: List,
    personal: List
) -> Dict:
    """
    Beräknar alla metrics för ett schema.

    Args:
        schema_rader: Lista med SchemaRad-objekt
        konflikter: Lista med Konflikt-objekt
        shifts: Lista med Shift-objekt
        personal: Lista med Person-objekt

    Returns:
        Dict med alla metrics
    """
    coverage = calculate_coverage_percent(schema_rader, shifts)
    overtime = calculate_overtime_hours(schema_rader, personal)
    violations = calculate_rule_violations(konflikter)
    cost = calculate_cost_kr(schema_rader, personal)
    quality = calculate_quality_score(coverage, violations, overtime, len(shifts))

    return {
        "coverage_percent": coverage,
        "overtime_hours": overtime,
        "rule_violations": violations,
        "cost_kr": cost,
        "quality_score": quality
    }
