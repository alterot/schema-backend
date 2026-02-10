"""
Schedule Analyzer - Helper functions for analyzing schedules and generating proposals.
Used by the tool endpoints to provide data-driven suggestions.
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict
from datetime import date


def find_conflicts(schema_rader: List, shifts: List, personal: List, bemanningsbehov: Dict) -> List[Dict]:
    """
    Analyze a generated schedule and find all conflicts/issues.

    Args:
        schema_rader: List of SchemaRad objects from solver
        shifts: List of Shift objects (requirements)
        personal: List of Person objects
        bemanningsbehov: Dict with 'vardag' and 'helg' requirements

    Returns:
        List of conflict dicts with typ, datum, pass, beskrivning, allvarlighetsgrad
    """
    conflicts = []

    # Build lookup: (datum, pass_typ) -> list of assigned names
    assignment_map = defaultdict(list)
    for rad in schema_rader:
        key = (rad.datum.isoformat(), rad.pass_typ.value)
        assignment_map[key] = rad.personal

    # Check each shift requirement for understaffing
    for shift in shifts:
        datum_str = shift.datum.isoformat()
        pass_str = shift.pass_typ.value
        assigned = assignment_map.get((datum_str, pass_str), [])

        for roll, krav in shift.kompetenskrav.items():
            # Count assigned with this role
            roll_lookup = {p.namn: p.roll for p in personal}
            count = sum(1 for name in assigned if roll_lookup.get(name, '') == roll)

            if count < krav:
                is_weekend = shift.datum.weekday() >= 5
                dag_typ = 'helg' if is_weekend else 'vardag'
                conflicts.append({
                    'typ': 'undermanning',
                    'datum': datum_str,
                    'pass': pass_str,
                    'beskrivning': f'Saknar {krav - count} {_roll_label(roll)} på {pass_str}pass ({dag_typ})',
                    'allvarlighetsgrad': 3 if (krav - count) >= 2 else 2,
                    'roll': roll,
                    'saknas': krav - count,
                })

    # Check for overtime per person
    pass_per_person = defaultdict(int)
    for rad in schema_rader:
        for namn in rad.personal:
            pass_per_person[namn] += 1

    max_pass_lookup = {p.namn: p.max_arbetspass_per_manad for p in personal}
    for namn, antal in pass_per_person.items():
        max_pass = max_pass_lookup.get(namn, 20)
        if antal > max_pass:
            conflicts.append({
                'typ': 'overtid',
                'datum': None,
                'pass': None,
                'beskrivning': f'{namn} har {antal} pass (max {max_pass} baserat på anställningsgrad)',
                'allvarlighetsgrad': 2,
                'person': namn,
                'overskott': antal - max_pass,
            })

    return conflicts


def suggest_solutions(conflicts: List[Dict], personal: List, schema_rader: List) -> List[Dict]:
    """
    Generate concrete solution proposals based on identified conflicts.

    Args:
        conflicts: List of conflict dicts from find_conflicts()
        personal: List of Person objects
        schema_rader: List of SchemaRad objects

    Returns:
        List of proposal dicts with id, beskrivning, kostnad_kr, paverkan
    """
    proposals = []
    proposal_id = 1

    # Count shifts per person to find who has room
    pass_per_person = defaultdict(int)
    for rad in schema_rader:
        for namn in rad.personal:
            pass_per_person[namn] += 1

    max_pass_lookup = {p.namn: p.max_arbetspass_per_manad for p in personal}
    roll_lookup = {p.namn: p.roll for p in personal}

    # Find people with capacity (fewer shifts than max)
    available_capacity = {}
    for p in personal:
        used = pass_per_person.get(p.namn, 0)
        remaining = p.max_arbetspass_per_manad - used
        if remaining > 0:
            available_capacity[p.namn] = {
                'remaining': remaining,
                'roll': p.roll,
                'namn': p.namn,
            }

    # Group undermanning conflicts
    undermanning = [c for c in conflicts if c['typ'] == 'undermanning']
    overtid = [c for c in conflicts if c['typ'] == 'overtid']

    if undermanning:
        # Proposal: redistribute from overstaffed shifts
        total_saknas = sum(c.get('saknas', 1) for c in undermanning)
        roller_som_saknas = set(c.get('roll', '') for c in undermanning)

        # Find available people per role
        for roll in roller_som_saknas:
            available_for_roll = [
                v for v in available_capacity.values() if v['roll'] == roll
            ]
            if available_for_roll:
                names = [a['namn'] for a in available_for_roll[:3]]
                total_capacity = sum(a['remaining'] for a in available_for_roll)
                proposals.append({
                    'id': proposal_id,
                    'beskrivning': f'Omfördela {_roll_label(roll)} med ledig kapacitet: '
                                   f'{", ".join(names)} (totalt {total_capacity} pass tillgängliga)',
                    'kostnad_kr': 0,
                    'paverkan': f'Kan täcka upp till {min(total_capacity, total_saknas)} av '
                                f'{total_saknas} underbemannade pass',
                })
                proposal_id += 1

        # Proposal: hire temp staff
        timlon = 350  # Average hourly rate
        timmar = total_saknas * 8
        kostnad = timmar * timlon
        proposals.append({
            'id': proposal_id,
            'beskrivning': f'Anlita vikarier för {total_saknas} obemannade pass',
            'kostnad_kr': kostnad,
            'paverkan': f'Täcker alla {total_saknas} underbemannade pass, '
                        f'kostnad ca {kostnad:,.0f} kr',
        })
        proposal_id += 1

    if overtid:
        total_overskott = sum(c.get('overskott', 0) for c in overtid)
        names = [c.get('person', '?') for c in overtid]
        proposals.append({
            'id': proposal_id,
            'beskrivning': f'Minska pass för överbelastade: {", ".join(names[:3])} '
                           f'(totalt {total_overskott} pass över gränsen)',
            'kostnad_kr': 0,
            'paverkan': f'Minskar övertid med {total_overskott * 8}h, '
                        f'förbättrar arbetsmiljö',
        })
        proposal_id += 1

    if not proposals:
        proposals.append({
            'id': 1,
            'beskrivning': 'Inga kritiska problem hittades — schemat ser bra ut',
            'kostnad_kr': 0,
            'paverkan': 'Ingen åtgärd krävs',
        })

    return proposals


def calculate_impact(metrics_before: Dict, metrics_after: Dict) -> Dict:
    """
    Calculate the difference between two sets of metrics.

    Args:
        metrics_before: Metrics dict before changes
        metrics_after: Metrics dict after changes

    Returns:
        Dict with diffs for each metric
    """
    return {
        'coverage_diff': round(metrics_after.get('coverage_percent', 0) - metrics_before.get('coverage_percent', 0), 1),
        'overtime_diff': round(metrics_after.get('overtime_hours', 0) - metrics_before.get('overtime_hours', 0), 1),
        'cost_diff': round(metrics_after.get('cost_kr', 0) - metrics_before.get('cost_kr', 0), 2),
        'quality_diff': metrics_after.get('quality_score', 0) - metrics_before.get('quality_score', 0),
        'violations_diff': metrics_after.get('rule_violations', 0) - metrics_before.get('rule_violations', 0),
    }


def _roll_label(roll: str) -> str:
    """Convert internal role name to Swedish display label."""
    labels = {
        'lakare': 'läkare',
        'sjukskoterska': 'sjuksköterska',
        'underskoterska': 'undersköterska',
    }
    return labels.get(roll, roll)
