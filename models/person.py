from dataclasses import dataclass, field
from typing import List, Dict
from datetime import date


@dataclass
class Franvaro:
    """Representerar en frånvaroperiod (semester, sjukdom, etc.)"""
    start: date
    slut: date
    typ: str = "semester"  # semester, sjuk, föräldraledig, etc.

    def overlaps(self, datum: date) -> bool:
        """Kontrollerar om ett datum ligger inom frånvaroperioden"""
        return self.start <= datum <= self.slut

    @classmethod
    def from_dict(cls, data: Dict) -> 'Franvaro':
        """Skapar Franvaro från dict"""
        return cls(
            start=date.fromisoformat(data['start']),
            slut=date.fromisoformat(data['slut']),
            typ=data.get('typ', 'semester')
        )


@dataclass
class Person:
    """Representerar en anställd på avdelningen"""
    id: int
    namn: str
    roll: str  # sjukskoterska, underskoterska, etc.
    anstallning: int  # 75, 100, etc. (procent)
    tillganglighet: List[str]  # ["Mon", "Tue", "Wed", "Thu", "Fri"]
    franvaro: List[Franvaro] = field(default_factory=list)
    exclude_pass_typer: List[str] = field(default_factory=list)  # ["natt", "kväll"]
    lasta_pass: List[Dict] = field(default_factory=list)  # [{"datum": date, "pass_typ": "dag"}]

    # Beräknade värden
    max_arbetspass_per_manad: int = field(init=False)
    max_timmar_per_manad: int = field(init=False)

    def __post_init__(self):
        """Beräknar max arbetstid baserat på anställningsgrad"""
        # Approximation: 100% ≈ 20 dagar/månad, 75% ≈ 15 dagar/månad
        self.max_arbetspass_per_manad = int((self.anstallning / 100) * 20)
        # Juridiskt korrekt: 100% = 40h/vecka ≈ 160h/månad (Arbetstidslagen § 5)
        self.max_timmar_per_manad = int((self.anstallning / 100) * 160)

    def ar_tillganglig(self, datum: date) -> bool:
        """Kontrollerar om personen är tillgänglig ett visst datum"""
        # Kontrollera veckodagstillgänglighet
        weekday_name = datum.strftime('%a')  # Mon, Tue, Wed, etc.
        if weekday_name not in self.tillganglighet:
            return False

        # Kontrollera frånvaro
        for f in self.franvaro:
            if f.overlaps(datum):
                return False

        return True

    @classmethod
    def from_dict(cls, data: Dict) -> 'Person':
        """Skapar Person från dict"""
        franvaro_list = [
            Franvaro.from_dict(f) for f in data.get('franvaro', [])
        ]

        # Auto-generera ID om det saknas (backward compat)
        person_id = data.get('id', abs(hash(data['namn'])) % 100000)

        return cls(
            id=person_id,
            namn=data['namn'],
            roll=data['roll'],
            anstallning=data['anstallning'],
            tillganglighet=data['tillganglighet'],
            franvaro=franvaro_list
        )
