from ortools.sat.python import cp_model
from typing import List, Dict, Set
from datetime import date, timedelta
from models import Person, Shift, PassTyp, Schedule, Konflikt


class ConstraintBuilder:
    """Bygger constraints för OR-Tools CP-SAT solver"""

    def __init__(self, model: cp_model.CpModel, personal: List[Person],
                 shifts: List[Shift], assignments: Dict):
        self.model = model
        self.personal = personal
        self.shifts = shifts
        self.assignments = assignments  # assignments[(person, shift)] = BoolVar

        # Bygg hjälpstrukturer
        self.person_index = {p.namn: p for p in personal}
        self.shifts_by_date = self._group_shifts_by_date()
        self.shifts_by_date_and_person = self._create_shift_dict()

    def _group_shifts_by_date(self) -> Dict[date, List[Shift]]:
        """Grupperar shifts per datum"""
        result = {}
        for shift in self.shifts:
            if shift.datum not in result:
                result[shift.datum] = []
            result[shift.datum].append(shift)
        return result

    def _create_shift_dict(self) -> Dict:
        """Skapar dict för snabb uppslagning av shifts per person och datum"""
        result = {}
        for person in self.personal:
            result[person.namn] = {}
            for shift in self.shifts:
                if shift.datum not in result[person.namn]:
                    result[person.namn][shift.datum] = []
                result[person.namn][shift.datum].append(shift)
        return result

    def add_harda_constraints(self):
        """Lägger till alla hårda constraints som MÅSTE uppfyllas"""
        self.constraint_en_person_ett_pass_per_dag()
        self.constraint_kompetenskrav()
        self.constraint_tillganglighet()
        self.constraint_franvaro()
        self.constraint_vilotid()
        self.constraint_max_arbetsdagar_i_rad()
        self.constraint_anstallningsgrad()

    def constraint_en_person_ett_pass_per_dag(self):
        """En person kan max jobba ett pass per dag"""
        for person in self.personal:
            for datum in self.shifts_by_date.keys():
                shifts_denna_dag = [
                    self.assignments[(person.namn, shift)]
                    for shift in self.shifts
                    if shift.datum == datum
                ]
                if shifts_denna_dag:
                    self.model.Add(sum(shifts_denna_dag) <= 1)

    def constraint_kompetenskrav(self):
        """Varje shift måste ha rätt antal personer med rätt kompetens"""
        for shift in self.shifts:
            for roll, antal_krav in shift.kompetenskrav.items():
                # Hitta alla personer med denna roll
                personer_med_roll = [
                    self.assignments[(p.namn, shift)]
                    for p in self.personal
                    if p.roll == roll
                ]
                if personer_med_roll:
                    # Exakt antal personer med rätt roll
                    self.model.Add(sum(personer_med_roll) == antal_krav)

    def constraint_tillganglighet(self):
        """Personer kan bara arbeta de dagar de är tillgängliga"""
        for person in self.personal:
            for shift in self.shifts:
                if not person.ar_tillganglig(shift.datum):
                    # Tvinga denna assignment till 0 (ej tilldelad)
                    self.model.Add(self.assignments[(person.namn, shift)] == 0)

    def constraint_franvaro(self):
        """Personer kan inte arbeta under frånvaroperioder (redan hanterat i ar_tillganglig)"""
        # Denna är redan hanterad i constraint_tillganglighet via ar_tillganglig()
        pass

    def constraint_vilotid(self):
        """Minst 11 timmar mellan pass"""
        # Sortera datum
        alla_datum = sorted(set(shift.datum for shift in self.shifts))

        for person in self.personal:
            for i in range(len(alla_datum) - 1):
                dag1 = alla_datum[i]
                dag2 = alla_datum[i + 1]

                # Endast om dagarna är konsekutiva
                if (dag2 - dag1).days == 1:
                    shifts_dag1 = [s for s in self.shifts if s.datum == dag1]
                    shifts_dag2 = [s for s in self.shifts if s.datum == dag2]

                    # För varje kombination av pass mellan dagarna
                    for s1 in shifts_dag1:
                        for s2 in shifts_dag2:
                            # Kontrollera om kombinationen bryter vilotid
                            if s1.pass_typ.bryter_vilotid(s2.pass_typ):
                                # Dessa två pass kan inte båda tilldelas samma person
                                self.model.Add(
                                    self.assignments[(person.namn, s1)] +
                                    self.assignments[(person.namn, s2)] <= 1
                                )

    def constraint_max_arbetsdagar_i_rad(self):
        """Max 5 arbetsdagar i rad"""
        MAX_DAGAR = 5

        alla_datum = sorted(set(shift.datum for shift in self.shifts))

        for person in self.personal:
            # För varje sekvens av 6 konsekutiva dagar
            for i in range(len(alla_datum) - MAX_DAGAR):
                # Ta 6 konsekutiva datum
                datum_sekvens = alla_datum[i:i + MAX_DAGAR + 1]

                # Kontrollera att de verkligen är konsekutiva
                ar_konsekutiv = all(
                    (datum_sekvens[j + 1] - datum_sekvens[j]).days == 1
                    for j in range(len(datum_sekvens) - 1)
                )

                if ar_konsekutiv:
                    # Hitta alla pass under dessa 6 dagar
                    alla_pass = [
                        self.assignments[(person.namn, shift)]
                        for shift in self.shifts
                        if shift.datum in datum_sekvens
                    ]

                    if alla_pass:
                        # Personen kan max arbeta 5 av dessa 6 dagar
                        self.model.Add(sum(alla_pass) <= MAX_DAGAR)

    def constraint_anstallningsgrad(self):
        """Respektera anställningsgrad (max antal pass per månad)"""
        # Gruppera shifts per månad
        shifts_per_manad = {}
        for shift in self.shifts:
            manad_key = (shift.datum.year, shift.datum.month)
            if manad_key not in shifts_per_manad:
                shifts_per_manad[manad_key] = []
            shifts_per_manad[manad_key].append(shift)

        # För varje person och månad
        for person in self.personal:
            for manad_key, shifts_i_manad in shifts_per_manad.items():
                assignments_i_manad = [
                    self.assignments[(person.namn, shift)]
                    for shift in shifts_i_manad
                ]
                if assignments_i_manad:
                    # Max antal pass enligt anställningsgrad
                    self.model.Add(
                        sum(assignments_i_manad) <= person.max_arbetspass_per_manad
                    )

    def add_mjuka_mal(self, objective_vars: List):
        """
        Lägger till mjuka mål (optimeringsmål).
        Returnerar variabler som ska maximeras.
        """
        self.mjukt_mal_jamn_helgfordelning(objective_vars)
        self.mjukt_mal_jamn_kvall_natt(objective_vars)

    def mjukt_mal_jamn_helgfordelning(self, objective_vars: List):
        """Försök fördela helgpass jämnt"""
        # Räkna helgpass per person
        for person in self.personal:
            helgpass = [
                self.assignments[(person.namn, shift)]
                for shift in self.shifts
                if shift.datum.weekday() >= 5  # Lördag eller söndag
            ]

            if helgpass:
                # Skapa en variabel för antal helgpass
                num_helgpass = self.model.NewIntVar(
                    0, len(helgpass),
                    f'helgpass_{person.namn}'
                )
                self.model.Add(num_helgpass == sum(helgpass))

                # Penalisera avvikelse från genomsnitt (implementeras i optimizer)
                # Här kan vi lägga till soft constraints om OR-Tools stödjer det

    def mjukt_mal_jamn_kvall_natt(self, objective_vars: List):
        """Försök fördela kväll- och nattpass jämnt"""
        for person in self.personal:
            kvall_natt_pass = [
                self.assignments[(person.namn, shift)]
                for shift in self.shifts
                if shift.pass_typ in [PassTyp.KVALL, PassTyp.NATT]
            ]

            if kvall_natt_pass:
                # Skapa variabel för antal kväll/nattpass
                num_kvall_natt = self.model.NewIntVar(
                    0, len(kvall_natt_pass),
                    f'kvall_natt_{person.namn}'
                )
                self.model.Add(num_kvall_natt == sum(kvall_natt_pass))
