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
        Alla rättvisemål jämför INOM SAMMA ROLL (SSK mot SSK, ej SSK mot läkare):
          1. Minimera överbemanning (vikt 3 per term)
          2. Jämn total-fördelning per roll (vikt 10)
          3. Jämn helgfördelning per roll (vikt 8)
          4. Jämn kvällsfördelning per roll (vikt 6)
          5. Jämn nattfördelning per roll (vikt 6)
          6. Undvik >3 kväll/natt i rad (vikt 4 per förekomst)
          7. Undvik bakåtrotation natt→ledig→dag (vikt 3 per förekomst)
        """
        penalty_terms = []

        # --- Mål 1a: Minimera undermanning (mjukt kompetenskrav) ---
        # Vikt 100 — högsta prioritet. Fyll bemanningskrav i första hand,
        # men om en roll inte räcker till ska övriga roller fortfarande schemaläggas.
        for shift in self.shifts:
            for roll, antal_krav in shift.kompetenskrav.items():
                personer_med_roll = [
                    self.assignments[(p.namn, shift)]
                    for p in self.personal
                    if p.roll == roll
                ]
                if personer_med_roll:
                    under = self.model.NewIntVar(
                        0, antal_krav,
                        f'under_{shift.datum}_{shift.pass_typ.value}_{roll}')
                    self.model.Add(under >= antal_krav - sum(personer_med_roll))
                    penalty_terms.append(under * 100)

        # --- Mål 1b: Minimera överbemanning ---
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

        # --- Mål 2: Jämn total-fördelning per roll ---
        # Viktigaste rättvisemålet: inom samma roll ska ingen ha markant fler/färre pass
        roller = set(p.roll for p in self.personal)
        for roll in roller:
            roll_personal = [p for p in self.personal if p.roll == roll]
            if len(roll_personal) < 2:
                continue
            total_vars = []
            for person in roll_personal:
                t = self.model.NewIntVar(0, len(self.shifts), f'total_{roll}_{person.namn}')
                self.model.Add(t == sum(
                    self.assignments[(person.namn, s)] for s in self.shifts
                ))
                total_vars.append(t)

            total_max = self.model.NewIntVar(0, len(self.shifts), f'total_{roll}_max')
            total_min = self.model.NewIntVar(0, len(self.shifts), f'total_{roll}_min')
            self.model.AddMaxEquality(total_max, total_vars)
            self.model.AddMinEquality(total_min, total_vars)
            total_spread = self.model.NewIntVar(0, len(self.shifts), f'total_{roll}_spread')
            self.model.Add(total_spread == total_max - total_min)
            penalty_terms.append(total_spread * 10)

        # --- Mål 3-5: Jämn fördelning per roll (helg/kväll/natt) ---
        helg_shifts = [s for s in self.shifts if s.datum.weekday() >= 5]
        kvall_shifts = [s for s in self.shifts if s.pass_typ == PassTyp.KVALL]
        natt_shifts = [s for s in self.shifts if s.pass_typ == PassTyp.NATT]

        roller = set(p.roll for p in self.personal)
        for roll in roller:
            roll_personal = [p for p in self.personal if p.roll == roll]
            if len(roll_personal) < 2:
                continue

            for label, shifts, vikt in [('helg', helg_shifts, 8), ('kvall', kvall_shifts, 6), ('natt', natt_shifts, 6)]:
                if not shifts:
                    continue
                spread_vars = []
                for person in roll_personal:
                    v = self.model.NewIntVar(0, len(shifts), f'{label}_{roll}_{person.namn}')
                    self.model.Add(v == sum(
                        self.assignments[(person.namn, s)] for s in shifts
                    ))
                    spread_vars.append(v)

                sp_max = self.model.NewIntVar(0, len(shifts), f'{label}_{roll}_max')
                sp_min = self.model.NewIntVar(0, len(shifts), f'{label}_{roll}_min')
                self.model.AddMaxEquality(sp_max, spread_vars)
                self.model.AddMinEquality(sp_min, spread_vars)
                spread = self.model.NewIntVar(0, len(shifts), f'{label}_{roll}_spread')
                self.model.Add(spread == sp_max - sp_min)
                penalty_terms.append(spread * vikt)

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
                personal=personal_lista,
                duration_hours=shift.duration_hours
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
        """Kontrollerar om pass är jämnt fördelade, per roll och kategori."""
        # Bygg roll-lookup och person-lookup
        roll_for = {p.namn: p.roll for p in self.personal}
        person_for = {p.namn: p for p in self.personal}

        # Samla per (roll, kategori)
        counts = defaultdict(lambda: defaultdict(int))  # (roll, kategori) -> {namn: antal}
        for rad in schedule.rader:
            for namn in rad.personal:
                roll = roll_for.get(namn, 'okänd')
                if rad.datum.weekday() >= 5:
                    counts[(roll, 'helg')][namn] += 1
                if rad.pass_typ == PassTyp.KVALL:
                    counts[(roll, 'kväll')][namn] += 1
                elif rad.pass_typ == PassTyp.NATT:
                    counts[(roll, 'natt')][namn] += 1

        dag_namn = {'Mon': 'mån', 'Tue': 'tis', 'Wed': 'ons', 'Thu': 'tor', 'Fri': 'fre', 'Sat': 'lör', 'Sun': 'sön'}

        for (roll, label), data in counts.items():
            if len(data) < 2:
                continue
            max_v = max(data.values())
            min_v = min(data.values())
            if max_v - min_v > 2:
                max_p = max(data, key=data.get)
                min_p = min(data, key=data.get)

                # Bygg förklaring med faktisk personaldata
                forklaring = self._forklara_obalans(max_p, min_p, label, person_for, dag_namn)

                schedule.lagg_till_konflikt(Konflikt(
                    datum=None,
                    pass_typ=None,
                    typ=f'obalanserad_{label}fordelning',
                    beskrivning=f'Ojämn {label}fördelning bland {roll}: {max_p} {max_v} {label}pass, {min_p} {min_v}. {forklaring}',
                    allvarlighetsgrad=1
                ))

    def _forklara_obalans(self, max_p, min_p, label, person_for, dag_namn):
        """Bygger en klartext-förklaring av varför fördelningen är ojämn."""
        delar = []
        for namn in [max_p, min_p]:
            person = person_for.get(namn)
            if not person:
                continue
            dagar = person.tillganglighet or []
            dagar_sv = [dag_namn.get(d, d) for d in dagar]
            helg_dagar = sum(1 for d in dagar if d in ('Sat', 'Sun'))

            if label == 'helg':
                helg_str = 'inkl. lör–sön' if helg_dagar == 2 else ('inkl. lör' if 'Sat' in dagar else ('inkl. sön' if 'Sun' in dagar else 'inga helgdagar'))
                delar.append(f'{namn} kan jobba {", ".join(dagar_sv)} ({helg_str})')
            elif label in ('kväll', 'natt'):
                excluded = person.exclude_pass_typer or []
                if label in excluded:
                    delar.append(f'{namn} har passrestriktion (ej {label})')
                elif person.anstallning < 100:
                    delar.append(f'{namn} är {person.anstallning}% (färre pass totalt)')
                else:
                    delar.append(f'{namn} kan jobba {", ".join(dagar_sv)}')

        if not delar:
            return ''

        orsak = '; '.join(delar)
        if label == 'helg':
            return f'{orsak}. Den med fler tillgängliga helgdagar får därför fler helgpass.'
        return f'{orsak}.'

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
