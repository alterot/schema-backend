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
        Sju mål med viktning balanserade för rättvisa:
          1. Minimera överbemanning (vikt 3 per term — många termer)
          2. Jämn fördelning av totalt antal pass (vikt 10)
          3. Jämn fördelning av helgpass (vikt 8)
          4. Jämn fördelning av kvällspass (vikt 6)
          5. Jämn fördelning av nattpass (vikt 6)
          6. Undvik >3 kväll- eller nattpass i rad (vikt 4 per förekomst)
          7. Undvik bakåtrotation natt→ledig→dag (vikt 3 per förekomst)
        """
        penalty_terms = []

        # --- Mål 1: Minimera överbemanning ---
        # Vikt 3 (sänkt från 10) — det finns ~90 shifts × roller = många termer
        # som annars dominerar och tränger ut rättvisemålen
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
                    penalty_terms.append(over * 3)

        # --- Mål 2: Jämn total-fördelning ---
        # Viktigaste rättvisemålet: ingen ska ha markant fler/färre pass totalt
        total_vars = []
        for person in self.personal:
            t = self.model.NewIntVar(0, len(self.shifts), f'total_{person.namn}')
            self.model.Add(t == sum(
                self.assignments[(person.namn, s)] for s in self.shifts
            ))
            total_vars.append(t)

        if total_vars:
            total_max = self.model.NewIntVar(0, len(self.shifts), 'total_max')
            total_min = self.model.NewIntVar(0, len(self.shifts), 'total_min')
            self.model.AddMaxEquality(total_max, total_vars)
            self.model.AddMinEquality(total_min, total_vars)
            total_spread = self.model.NewIntVar(0, len(self.shifts), 'total_spread')
            self.model.Add(total_spread == total_max - total_min)
            penalty_terms.append(total_spread * 10)

        # --- Mål 3: Jämn helgfördelning ---
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
            penalty_terms.append(helg_spread * 8)

        # --- Mål 4: Jämn kvällsfördelning (separat från natt) ---
        kvall_shifts = [s for s in self.shifts if s.pass_typ == PassTyp.KVALL]
        if kvall_shifts:
            kvall_vars = []
            for person in self.personal:
                kv = self.model.NewIntVar(0, len(kvall_shifts), f'kvall_{person.namn}')
                self.model.Add(kv == sum(
                    self.assignments[(person.namn, s)] for s in kvall_shifts
                ))
                kvall_vars.append(kv)

            kvall_max = self.model.NewIntVar(0, len(kvall_shifts), 'kvall_max')
            kvall_min = self.model.NewIntVar(0, len(kvall_shifts), 'kvall_min')
            self.model.AddMaxEquality(kvall_max, kvall_vars)
            self.model.AddMinEquality(kvall_min, kvall_vars)
            kvall_spread = self.model.NewIntVar(0, len(kvall_shifts), 'kvall_spread')
            self.model.Add(kvall_spread == kvall_max - kvall_min)
            penalty_terms.append(kvall_spread * 6)

        # --- Mål 5: Jämn nattfördelning (separat från kväll) ---
        natt_shifts = [s for s in self.shifts if s.pass_typ == PassTyp.NATT]
        if natt_shifts:
            natt_vars = []
            for person in self.personal:
                n = self.model.NewIntVar(0, len(natt_shifts), f'natt_{person.namn}')
                self.model.Add(n == sum(
                    self.assignments[(person.namn, s)] for s in natt_shifts
                ))
                natt_vars.append(n)

            natt_max = self.model.NewIntVar(0, len(natt_shifts), 'natt_max')
            natt_min = self.model.NewIntVar(0, len(natt_shifts), 'natt_min')
            self.model.AddMaxEquality(natt_max, natt_vars)
            self.model.AddMinEquality(natt_min, natt_vars)
            natt_spread = self.model.NewIntVar(0, len(natt_shifts), 'natt_spread')
            self.model.Add(natt_spread == natt_max - natt_min)
            penalty_terms.append(natt_spread * 6)

        # --- Mål 6: Undvik >3 kväll- eller nattpass i rad ---
        # Lång serie av samma obekväma passtyp är dåligt för hälsan
        alla_datum = sorted(set(s.datum for s in self.shifts))
        for person in self.personal:
            for i in range(len(alla_datum) - 3):
                datum_4 = alla_datum[i:i + 4]
                # Kontrollera att de 4 dagarna är konsekutiva
                if all((datum_4[j + 1] - datum_4[j]).days == 1 for j in range(3)):
                    # Kvällsstreak: alla 4 dagar kväll?
                    kvall_4 = [
                        self.assignments[(person.namn, s)]
                        for s in self.shifts
                        if s.datum in datum_4 and s.pass_typ == PassTyp.KVALL
                    ]
                    if len(kvall_4) == 4:
                        streak_kv = self.model.NewBoolVar(
                            f'kv_streak_{person.namn}_{datum_4[0]}')
                        self.model.Add(sum(kvall_4) >= 4).OnlyEnforceIf(streak_kv)
                        self.model.Add(sum(kvall_4) < 4).OnlyEnforceIf(streak_kv.Not())
                        penalty_terms.append(streak_kv * 4)

                    # Nattstreak: alla 4 dagar natt?
                    natt_4 = [
                        self.assignments[(person.namn, s)]
                        for s in self.shifts
                        if s.datum in datum_4 and s.pass_typ == PassTyp.NATT
                    ]
                    if len(natt_4) == 4:
                        streak_n = self.model.NewBoolVar(
                            f'n_streak_{person.namn}_{datum_4[0]}')
                        self.model.Add(sum(natt_4) >= 4).OnlyEnforceIf(streak_n)
                        self.model.Add(sum(natt_4) < 4).OnlyEnforceIf(streak_n.Not())
                        penalty_terms.append(streak_n * 4)

        # --- Mål 7: Undvik bakåtrotation (natt → ledig → dag) ---
        # Natt dag 1, ledig dag 2, dagpass dag 3 = dålig cirkadisk övergång
        for person in self.personal:
            for i in range(len(alla_datum) - 2):
                dag1 = alla_datum[i]
                dag3 = alla_datum[i + 2]
                if (dag3 - dag1).days == 2:
                    natt_s = next(
                        (s for s in self.shifts
                         if s.datum == dag1 and s.pass_typ == PassTyp.NATT), None)
                    dag_s = next(
                        (s for s in self.shifts
                         if s.datum == dag3 and s.pass_typ == PassTyp.DAG), None)
                    if natt_s and dag_s:
                        bad_rot = self.model.NewBoolVar(
                            f'bad_rot_{person.namn}_{dag1}')
                        self.model.Add(
                            self.assignments[(person.namn, natt_s)] +
                            self.assignments[(person.namn, dag_s)] >= 2
                        ).OnlyEnforceIf(bad_rot)
                        self.model.Add(
                            self.assignments[(person.namn, natt_s)] +
                            self.assignments[(person.namn, dag_s)] < 2
                        ).OnlyEnforceIf(bad_rot.Not())
                        penalty_terms.append(bad_rot * 3)

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
                            beskrivning=f'{faktisk - krav} extra {roll} — överväg flex/ledig',
                            allvarlighetsgrad=0
                        ))

        # Kontrollera fördelning per kategori
        self._kontrollera_fordelning(schedule)

    def _kontrollera_fordelning(self, schedule: Schedule):
        """Kontrollerar om pass är jämnt fördelade, separat per kategori."""
        helg_per_person = defaultdict(int)
        kvall_per_person = defaultdict(int)
        natt_per_person = defaultdict(int)

        for rad in schedule.rader:
            for person_namn in rad.personal:
                if rad.datum.weekday() >= 5:
                    helg_per_person[person_namn] += 1
                if rad.pass_typ == PassTyp.KVALL:
                    kvall_per_person[person_namn] += 1
                elif rad.pass_typ == PassTyp.NATT:
                    natt_per_person[person_namn] += 1

        for label, data in [('helg', helg_per_person), ('kväll', kvall_per_person), ('natt', natt_per_person)]:
            if not data:
                continue
            max_v = max(data.values())
            min_v = min(data.values(), default=0)
            if max_v - min_v > 2:
                max_p = max(data, key=data.get)
                min_p = min(data, key=data.get)
                schedule.lagg_till_konflikt(Konflikt(
                    datum=None,
                    pass_typ=None,
                    typ=f'obalanserad_{label}fordelning',
                    beskrivning=f'Ojämn {label}fördelning: {max_p} {max_v}, {min_p} {min_v}',
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
