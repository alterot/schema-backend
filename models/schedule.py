from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import date
from .shift import Shift, PassTyp


@dataclass
class Konflikt:
    """Representerar en konflikt eller överträdelse i schemat"""
    datum: date
    pass_typ: Optional[PassTyp]
    typ: str  # "undermanning", "vilotid", "anstallningsgrad", etc.
    beskrivning: str
    allvarlighetsgrad: int = 1  # 1 = varning, 2 = allvarlig, 3 = kritisk

    def to_dict(self) -> Dict:
        """Konverterar till dict for JSON-svar"""
        return {
            'datum': self.datum.isoformat() if self.datum else None,
            'pass': self.pass_typ.value if self.pass_typ else None,
            'typ': self.typ,
            'beskrivning': self.beskrivning,
            'allvarlighetsgrad': self.allvarlighetsgrad
        }


@dataclass
class SchemaRad:
    """Representerar en rad i schemat (ett pass med tilldelade personer)"""
    datum: date
    pass_typ: PassTyp
    avdelning: str
    personal: List[str]  # Lista med personnamn
    duration_hours: int = 8  # Passlängd i timmar

    def to_dict(self) -> Dict:
        """Konverterar till dict för JSON-svar"""
        return {
            'datum': self.datum.isoformat(),
            'pass': self.pass_typ.value,
            'avdelning': self.avdelning,
            'personal': self.personal
        }


@dataclass
class Schedule:
    """Representerar ett komplett schema för en period"""
    rader: List[SchemaRad] = field(default_factory=list)
    konflikter: List[Konflikt] = field(default_factory=list)
    statistik: Dict = field(default_factory=dict)

    def lagg_till_rad(self, rad: SchemaRad):
        """Lägger till en schemarad"""
        self.rader.append(rad)

    def lagg_till_konflikt(self, konflikt: Konflikt):
        """Lägger till en konflikt"""
        self.konflikter.append(konflikt)

    def to_dict(self) -> Dict:
        """Konverterar till dict för JSON-svar"""
        return {
            'schema': [rad.to_dict() for rad in self.rader],
            'konflikter': [k.to_dict() for k in self.konflikter],
            'statistik': self.statistik
        }

    def berakna_statistik(self, personal: List['Person']):
        """Beräknar statistik för schemat"""
        from collections import defaultdict

        # Räkna pass per person
        pass_per_person = defaultdict(lambda: {
            'totalt': 0,
            'dag': 0,
            'kväll': 0,
            'natt': 0,
            'helger': 0
        })

        for rad in self.rader:
            for person_namn in rad.personal:
                pass_per_person[person_namn]['totalt'] += 1
                pass_per_person[person_namn][rad.pass_typ.value] += 1

                # Räkna helgpass
                if rad.datum.weekday() >= 5:  # Lördag eller söndag
                    pass_per_person[person_namn]['helger'] += 1

        self.statistik = {
            'totalt_antal_pass': len(self.rader),
            'antal_konflikter': len(self.konflikter),
            'pass_per_person': dict(pass_per_person)
        }
