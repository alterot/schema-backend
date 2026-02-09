from dataclasses import dataclass
from typing import Dict
from datetime import date, datetime, timedelta
from enum import Enum


class PassTyp(Enum):
    """Definierar olika typer av arbetspass"""
    DAG = "dag"
    KVALL = "kväll"
    NATT = "natt"

    def start_tid(self) -> int:
        """Returnerar starttid i timmar (0-23)"""
        mapping = {
            PassTyp.DAG: 7,
            PassTyp.KVALL: 15,
            PassTyp.NATT: 23
        }
        return mapping[self]

    def slut_tid(self) -> int:
        """Returnerar sluttid i timmar (0-23)"""
        mapping = {
            PassTyp.DAG: 15,
            PassTyp.KVALL: 23,
            PassTyp.NATT: 7  # Nästa dag
        }
        return mapping[self]

    def langd_timmar(self) -> int:
        """Returnerar passets längd i timmar"""
        return 8

    def bryter_vilotid(self, nasta_pass_typ: 'PassTyp') -> bool:
        """
        Kontrollerar om övergång till nästa pass bryter 11h vilotid.
        Returnerar True om vilotiden bryts.
        """
        slut = self.slut_tid()
        nasta_start = nasta_pass_typ.start_tid()

        # Hantera övergång mellan dagar
        if self == PassTyp.NATT:
            # Nattpass slutar kl 7 nästa dag
            timmar_mellan = nasta_start + 24 - 7
        elif nasta_pass_typ == PassTyp.NATT and self == PassTyp.KVALL:
            # Kvällspass slutar 23, nattpass börjar 23
            timmar_mellan = 0
        else:
            timmar_mellan = (nasta_start - slut) % 24

        return timmar_mellan < 11


@dataclass
class Shift:
    """Representerar ett arbetspass som behöver bemannas"""
    datum: date
    pass_typ: PassTyp
    avdelning: str
    kompetenskrav: Dict[str, int]  # {"sjukskoterska": 2, "underskoterska": 3}

    def __hash__(self):
        """Gör Shift hashbar för användning i sets och dicts"""
        return hash((self.datum, self.pass_typ.value, self.avdelning))

    def __eq__(self, other):
        if not isinstance(other, Shift):
            return False
        return (self.datum == other.datum and
                self.pass_typ == other.pass_typ and
                self.avdelning == other.avdelning)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Shift':
        """Skapar Shift från dict"""
        return cls(
            datum=date.fromisoformat(data['datum']),
            pass_typ=PassTyp(data['pass']),
            avdelning=data['avdelning'],
            kompetenskrav=data['kompetenskrav']
        )
