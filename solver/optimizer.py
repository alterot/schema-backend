from ortools.sat.python import cp_model
from typing import List, Dict, Tuple
from models import Person, Shift, Schedule, SchemaRad, Konflikt, PassTyp
from .constraints import ConstraintBuilder
from collections import defaultdict


class SchemaOptimizer:
    """
    Huvudklass för schemaoptimering med OR-Tools CP-SAT.
    Tar emot personal och shifts, returnerar ett optimerat schema.
    """

    def __init__(self, personal: List[Person], shifts: List[Shift]):
        self.personal = personal
        self.shifts = shifts
        self.model = cp_model.CpModel()
        self.assignments = {}  # (person_namn, shift) -> BoolVar
        self.solver = cp_model.CpSolver()

        # Konfiguration
        self.solver.parameters.max_time_in_seconds = 30.0
        self.solver.parameters.log_search_progress = False
        self.solver.parameters.random_seed = 42  # Deterministisk: samma input → samma schema

    def optimera(self) -> Schedule:
        """
        Huvudmetod som kör optimeringen.
        Returnerar ett Schedule-objekt med resultat och eventuella konflikter.
        """
        # Steg 1: Skapa beslutvariabler
        self._skapa_variabler()

        # Steg 2: Lägg till constraints
        constraint_builder = ConstraintBuilder(
            self.model, self.personal, self.shifts, self.assignments
        )
        constraint_builder.add_harda_constraints()

        # Steg 3: Definiera objektfunktion (minimera överbemanning + jämn fördelning)
        self._definiera_objektfunktion()

        # Steg 5: Lös problemet
        status = self.solver.Solve(self.model)

        # Steg 6: Bygg resultat
        schedule = self._bygg_schedule(status)

        # Steg 7: Beräkna statistik
        schedule.berakna_statistik(self.personal)

        return schedule

    def _skapa_variabler(self):
        """Skapar beslutvariabler för varje person-shift kombination"""
        for person in self.personal:
            for shift in self.shifts:
                # Skapa en boolean variabel: 1 = person arbetar detta shift, 0 = inte
                var_name = f'{person.namn}_{shift.datum}_{shift.pass_typ.value}'
                self.assignments[(person.namn, shift)] = self.model.NewBoolVar(var_name)

    def _definiera_objektfunktion(self):
        """
        Definierar vad vi vill optimera.
        Tre mål med viktning:
          1. Minimera överbemanning (vikt 10)
          2. Jämn fördelning av helgpass (vikt 5)
          3. Jämn fördelning av kväll/nattpass (vikt 3)
        """
        penalty_terms = []

        # --- Mål 1: Minimera överbemanning ---
        for shift in self.shifts:
            for roll, antal_krav in shift.kompetenskrav.items():
                personer_med_roll = [
                    self.assignments[(p.namn, shift)]
                    for p in self.personal
                    if p.roll == roll
                ]
                if personer_med_roll:
                    over = self.model.NewIntVar(
                        0, len(personer_med_roll),
                        f'over_{shift.datum}_{shift.pass_typ.value}_{roll}')
                    self.model.Add(over >= sum(personer_med_roll) - antal_krav)
                    penalty_terms.append(over * 10)

        # --- Mål 2: Jämn helgfördelning ---
        helg_shifts = [s for s in self.shifts if s.datum.weekday() >= 5]
        if helg_shifts:
            helgpass_vars = []
            for person in self.personal:
                h = self.model.NewIntVar(0, len(helg_shifts), f'helg_{person.namn}')
                self.model.Add(h == sum(
                    self.assignments[(person.namn, s)] for s in helg_shifts
                ))
                helgpass_vars.append(h)

            helg_max = self.model.NewIntVar(0, len(helg_shifts), 'helg_max')
            helg_min = self.model.NewIntVar(0, len(helg_shifts), 'helg_min')
            self.model.AddMaxEquality(helg_max, helgpass_vars)
            self.model.AddMinEquality(helg_min, helgpass_vars)
            helg_spread = self.model.NewIntVar(0, len(helg_shifts), 'helg_spread')
            self.model.Add(helg_spread == helg_max - helg_min)
            penalty_terms.append(helg_spread * 5)

        # --- Mål 3: Jämn kväll/nattfördelning ---
        kn_shifts = [s for s in self.shifts if s.pass_typ in [PassTyp.KVALL, PassTyp.NATT]]
        if kn_shifts:
            kn_vars = []
            for person in self.personal:
                kn = self.model.NewIntVar(0, len(kn_shifts), f'kn_{person.namn}')
                self.model.Add(kn == sum(
                    self.assignments[(person.namn, s)] for s in kn_shifts
                ))
                kn_vars.append(kn)

            kn_max = self.model.NewIntVar(0, len(kn_shifts), 'kn_max')
            kn_min = self.model.NewIntVar(0, len(kn_shifts), 'kn_min')
            self.model.AddMaxEquality(kn_max, kn_vars)
            self.model.AddMinEquality(kn_min, kn_vars)
            kn_spread = self.model.NewIntVar(0, len(kn_shifts), 'kn_spread')
            self.model.Add(kn_spread == kn_max - kn_min)
            penalty_terms.append(kn_spread * 3)

        # Minimera sammanlagd penalty
        if penalty_terms:
            self.model.Minimize(sum(penalty_terms))

    def _bygg_schedule(self, status) -> Schedule:
        """Bygger ett Schedule-objekt från solver-resultatet"""
        schedule = Schedule()

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            # Lösning hittad
            self._lagg_till_schemarader(schedule)
            self._identifiera_konflikter(schedule)

        elif status == cp_model.INFEASIBLE:
            # Ingen lösning möjlig
            schedule.lagg_till_konflikt(Konflikt(
                datum=min(s.datum for s in self.shifts) if self.shifts else None,
                pass_typ=None,
                typ='inga_losningar',
                beskrivning='Ingen giltig lösning hittades. '
                           'Problemet är överspezificerat (för många constraints).',
                allvarlighetsgrad=3
            ))
            self._identifiera_orsakar_till_infeasibility(schedule)

        else:
            # Timeout eller annat problem
            schedule.lagg_till_konflikt(Konflikt(
                datum=None,
                pass_typ=None,
                typ='timeout',
                beskrivning='Tidsfristen överskreds innan en optimal lösning hittades.',
                allvarlighetsgrad=2
            ))

        return schedule

    def _lagg_till_schemarader(self, schedule: Schedule):
        """Lägger till schemarader från lösningen"""
        # Gruppera per shift
        shifts_med_personal = defaultdict(list)

        for (person_namn, shift), var in self.assignments.items():
            if self.solver.Value(var) == 1:
                shifts_med_personal[shift].append(person_namn)

        # Skapa schemarader
        for shift in self.shifts:
            personal_lista = shifts_med_personal.get(shift, [])
            schema_rad = SchemaRad(
                datum=shift.datum,
                pass_typ=shift.pass_typ,
                avdelning=shift.avdelning,
                personal=personal_lista
            )
            schedule.lagg_till_rad(schema_rad)

    def _identifiera_konflikter(self, schedule: Schedule):
        """
        Identifierar och dokumenterar konflikter i schemat.
        Även om en lösning hittas kan det finnas mjuka konflikter.
        """
        # Kontrollera undermanning
        for rad in schedule.rader:
            # Hitta motsvarande shift-krav
            matching_shift = next(
                (s for s in self.shifts
                 if s.datum == rad.datum and s.pass_typ == rad.pass_typ),
                None
            )

            if matching_shift:
                # Räkna antal per roll
                personal_per_roll = defaultdict(int)
                for person_namn in rad.personal:
                    person = next(p for p in self.personal if p.namn == person_namn)
                    personal_per_roll[person.roll] += 1

                # Jämför med krav
                for roll, krav in matching_shift.kompetenskrav.items():
                    faktisk = personal_per_roll.get(roll, 0)
                    if faktisk < krav:
                        schedule.lagg_till_konflikt(Konflikt(
                            datum=rad.datum,
                            pass_typ=rad.pass_typ,
                            typ='undermanning',
                            beskrivning=f'Saknar {krav - faktisk} {roll}',
                            allvarlighetsgrad=3
                        ))
                    elif faktisk > krav:
                        schedule.lagg_till_konflikt(Konflikt(
                            datum=rad.datum,
                            pass_typ=rad.pass_typ,
                            typ='overbemanning',
                            beskrivning=f'{faktisk - krav} för många {roll}',
                            allvarlighetsgrad=1
                        ))

        # Kontrollera helgfördelning
        self._kontrollera_helgfordelning(schedule)

        # Kontrollera kväll/nattfördelning
        self._kontrollera_kvall_natt_fordelning(schedule)

    def _kontrollera_helgfordelning(self, schedule: Schedule):
        """Kontrollerar om helgpass är jämnt fördelade"""
        helgpass_per_person = defaultdict(int)

        for rad in schedule.rader:
            if rad.datum.weekday() >= 5:  # Lördag eller söndag
                for person_namn in rad.personal:
                    helgpass_per_person[person_namn] += 1

        if helgpass_per_person:
            genomsnitt = sum(helgpass_per_person.values()) / len(self.personal)
            max_helg = max(helgpass_per_person.values())
            min_helg = min(helgpass_per_person.values(), default=0)

            if max_helg - min_helg > 2:
                # Ojämn fördelning
                max_person = max(helgpass_per_person, key=helgpass_per_person.get)
                schedule.lagg_till_konflikt(Konflikt(
                    datum=None,
                    pass_typ=None,
                    typ='obalanserad_helgfordelning',
                    beskrivning=f'Ojämn helgfördelning: {max_person} har {max_helg} helgpass '
                               f'medan andra har {min_helg}',
                    allvarlighetsgrad=1
                ))

    def _kontrollera_kvall_natt_fordelning(self, schedule: Schedule):
        """Kontrollerar om kväll/nattpass är jämnt fördelade"""
        kvall_natt_per_person = defaultdict(int)

        for rad in schedule.rader:
            if rad.pass_typ in [PassTyp.KVALL, PassTyp.NATT]:
                for person_namn in rad.personal:
                    kvall_natt_per_person[person_namn] += 1

        if kvall_natt_per_person:
            max_kn = max(kvall_natt_per_person.values())
            min_kn = min(kvall_natt_per_person.values(), default=0)

            if max_kn - min_kn > 3:
                max_person = max(kvall_natt_per_person, key=kvall_natt_per_person.get)
                schedule.lagg_till_konflikt(Konflikt(
                    datum=None,
                    pass_typ=None,
                    typ='obalanserad_kvall_natt',
                    beskrivning=f'Ojämn fördelning av kväll/nattpass: '
                               f'{max_person} har {max_kn} pass medan andra har {min_kn}',
                    allvarlighetsgrad=1
                ))

    def _identifiera_orsakar_till_infeasibility(self, schedule: Schedule):
        """
        Försöker identifiera varför ingen lösning kunde hittas.
        Detta är komplext och kräver analys av constraints.
        """
        # Kontrollera grundläggande kapacitet
        total_pass_behov = len(self.shifts)
        total_personer = len(self.personal)

        # Beräkna max tillgängliga arbetspass
        max_tillgangliga_pass = sum(p.max_arbetspass_per_manad for p in self.personal)

        if max_tillgangliga_pass < total_pass_behov:
            schedule.lagg_till_konflikt(Konflikt(
                datum=None,
                pass_typ=None,
                typ='otillracklig_kapacitet',
                beskrivning=f'För få personer: Behöver {total_pass_behov} pass '
                           f'men max kapacitet är {max_tillgangliga_pass} pass',
                allvarlighetsgrad=3
            ))

        # Kontrollera kompetenskrav per shift
        for shift in self.shifts:
            for roll, antal_krav in shift.kompetenskrav.items():
                tillgangliga = [
                    p for p in self.personal
                    if p.roll == roll and p.ar_tillganglig(shift.datum)
                ]
                if len(tillgangliga) < antal_krav:
                    schedule.lagg_till_konflikt(Konflikt(
                        datum=shift.datum,
                        pass_typ=shift.pass_typ,
                        typ='otillracklig_kompetens',
                        beskrivning=f'För få {roll}: Behöver {antal_krav} men '
                                   f'endast {len(tillgangliga)} är tillgängliga',
                        allvarlighetsgrad=3
                    ))

        # Kontrollera frånvaro
        franvaro_konflikter = self._analysera_franvaro()
        for konflikt in franvaro_konflikter:
            schedule.lagg_till_konflikt(konflikt)

    def _analysera_franvaro(self) -> List[Konflikt]:
        """Analyserar om frånvaro orsakar problem"""
        konflikter = []

        # Gruppera shifts per datum och roll
        shifts_per_datum_roll = defaultdict(lambda: defaultdict(int))
        for shift in self.shifts:
            for roll, antal in shift.kompetenskrav.items():
                shifts_per_datum_roll[shift.datum][roll] += antal

        # Kontrollera tillgänglighet per datum och roll
        for datum, roller in shifts_per_datum_roll.items():
            for roll, behov in roller.items():
                tillgangliga = [
                    p for p in self.personal
                    if p.roll == roll and p.ar_tillganglig(datum)
                ]

                if len(tillgangliga) < behov:
                    # Räkna hur många som är frånvarande
                    franvarande = [
                        p for p in self.personal
                        if p.roll == roll and not p.ar_tillganglig(datum)
                    ]

                    if franvarande:
                        konflikter.append(Konflikt(
                            datum=datum,
                            pass_typ=None,
                            typ='franvaro_konflikt',
                            beskrivning=f'Frånvaro påverkar bemanningen: '
                                       f'{len(franvarande)} {roll} frånvarande, '
                                       f'behöver {behov} men har endast {len(tillgangliga)}',
                            allvarlighetsgrad=3
                        ))

        return konflikter
