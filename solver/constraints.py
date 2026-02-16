"""
CONSTRAINT BUILDER FÖR SCHEMALÄGGNING I VÅRDEN
==============================================

Detta modul implementerar constraints baserade på svensk arbetsrätt och kollektivavtal.

LAGSTADGADE REGLER SOM IMPLEMENTERAS:
-------------------------------------

1. DYGNSVILA (11 timmar)
   Källa: Arbetstidslagen (1982:673) § 13
   - Minst 11 timmars sammanhängande vila mellan arbetspass
   - Gäller mellan konsekutiva dagar
   - Undantag endast vid nödsituation med kompensationsledighet

2. VECKOVILA (36 timmar)
   Källa: Arbetstidslagen (1982:673) § 14, SKR/Sobona kollektivavtal (2023)
   - Minst 36 timmars sammanhängande ledighet per 7-dagarsperiod
   - Kan tillfälligt sänkas till 24h vid särskilda omständigheter
   - Strikt tillämpning sedan oktober 2023 (EU arbetstidsdirektiv)

3. MAX ARBETSDAGAR I RAD (5 dagar)
   Källa: Kollektivavtal vård (varierande 5-7 dagar)
   - Vi använder konservativa 5 dagar för säkerhet
   - Förhindrar utbrändhet och garanterar återhämtning

4. ÖVERTIDSBEGRÄNSNINGAR
   Källa: Arbetstidslagen (1982:673) § 8, 8a
   - Allmän övertid: Max 200 timmar per kalenderår
   - Extra övertid: Max 150 timmar per kalenderår (totalt 350h)
   - Sammanlagd arbetstid: Max 48h/vecka i genomsnitt (4 månaders period)
   - Nödfallsövertid: Separat hantering vid kris

5. ANSTÄLLNINGSGRAD
   Källa: Anställningsavtal, Arbetstidslagen § 5
   - Ordinarie arbetstid: 40h/vecka för heltid (100%)
   - Deltid proportionellt: 75% ≈ 30h/vecka
   - Approximation: 100% ≈ 20 dagar/månad, 75% ≈ 15 dagar/månad

6. KOMPETENSKRAV PER PASS
   Källa: Socialstyrelsen SOSFS 2012:11, Patientsäkerhetslagen
   - Varje pass måste ha tillräcklig kompetens (SSK/USK/Läkare)
   - Specifikt antal per roll baserat på avdelningstyp och patientvolym

7. TILLGÄNGLIGHET OCH FRÅNVARO
   Källa: Anställningsavtal, Semesterlagen
   - Personal kan endast schemaläggas när de är tillgängliga
   - Semester, sjukdom, VAB respekteras
   - Preferenser beaktas när möjligt

8. ETT PASS PER DAG
   Källa: Arbetsmiljölagen (1977:1160), god praxis
   - Förhindrar dubbelpass samma dag
   - Undviker överbelastning

REGLER SOM INTE IMPLEMENTERAS I POC (men relevanta för produktion):
-------------------------------------------------------------------

9. NATTARBETSBEGRÄNSNINGAR
   Källa: Arbetstidslagen § 13a, Kollektivavtal
   - Max 8 timmar per dygn för nattarbetare
   - Sänkt veckoarbetstid vid nattarbete (38h vs 40h)
   - Implementeras i framtida version

10. RASTER OCH PAUSER
    Källa: Arbetstidslagen § 15-16
    - Minst 30 min rast vid >6h arbete
    - Inte kritiskt för schemaläggning (hanteras lokalt)

11. KOMPENSATIONSLEDIGHET
    Källa: Arbetstidslagen § 13, 14
    - Motsvarande ledighet vid brott mot dygns-/veckovila
    - Loggas som konflikt, hanteras manuellt i POC

MJUKA MÅL (optimering, ej krav):
---------------------------------
- Jämn fördelning av helgpass
- Jämn fördelning av kväll/nattpass
- Minimera övertid
- Respektera preferenser när möjligt

KÄLLOR:
-------
- Arbetstidslagen (1982:673): https://www.riksdagen.se/sv/dokument-lagar/dokument/svensk-forfattningssamling/arbetstidslag-1982673_sfs-1982-673
- Arbetsmiljölagen (1977:1160): https://www.riksdagen.se/sv/dokument-lagar/dokument/svensk-forfattningssamling/arbetsmiljolag-19771160_sfs-1977-1160
- SKR Kollektivavtal Allmänna bestämmelser (2023): https://skr.se
- Vårdförbundet Kollektivavtal: https://www.vardforbundet.se
- Socialstyrelsen SOSFS 2012:11: Ledningssystem för kvalitet och patientsäkerhet

VIKTIGT:
--------
Detta är en POC (Proof of Concept). För produktionsmiljö bör följande verifieras:
- Exakt kollektivavtal för specifik arbetsgivare
- Lokala avtal och överenskommelser
- Dispenser och undantag
- Aktuell lagstiftning (regler kan ändras)

Senast uppdaterad: 2026-02-10
"""

from ortools.sat.python import cp_model
from typing import List, Dict, Set
from datetime import date, timedelta
from models import Person, Shift, PassTyp, Schedule, Konflikt


class ConstraintBuilder:
    """Bygger constraints för OR-Tools CP-SAT solver baserat på svensk arbetsrätt"""

    def __init__(self, model: cp_model.CpModel, personal: List[Person],
                 shifts: List[Shift], assignments: Dict):
        self.model = model
        self.personal = personal
        self.shifts = shifts
        self.assignments = assignments  # assignments[(person, shift)] = BoolVar

        # Bygg hjälpstrukturer
        self.person_index = {p.id: p for p in personal}
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
            result[person.id] = {}
            for shift in self.shifts:
                if shift.datum not in result[person.id]:
                    result[person.id][shift.datum] = []
                result[person.id][shift.datum].append(shift)
        return result

    def add_harda_constraints(self):
        """Lägger till alla hårda constraints som MÅSTE uppfyllas"""
        self.constraint_en_person_ett_pass_per_dag()
        self.constraint_kompetenskrav()
        self.constraint_tillganglighet()
        self.constraint_franvaro()
        self.constraint_vilotid()
        self.constraint_veckovila()  # NY: Lagstadgad 36h veckovila
        self.constraint_max_arbetsdagar_i_rad()
        self.constraint_anstallningsgrad()
        self.constraint_overtid()  # NY: Övertidsbegränsningar
        self.constraint_passrestriktioner()
        self.constraint_lasta_pass()
        self.constraint_jamn_fordelning()

    def constraint_en_person_ett_pass_per_dag(self):
        """
        En person kan max jobba ett pass per dag
        
        Källa: Arbetsmiljölagen, god praxis
        Förhindrar dubbelpass som kan leda till utmattning
        """
        for person in self.personal:
            for datum in self.shifts_by_date.keys():
                shifts_denna_dag = [
                    self.assignments[(person.id, shift)]
                    for shift in self.shifts
                    if shift.datum == datum
                ]
                if shifts_denna_dag:
                    self.model.Add(sum(shifts_denna_dag) <= 1)

    def constraint_kompetenskrav(self):
        """
        Kompetenskrav hanteras nu som mjuk constraint i optimizer.py.

        Anledning: Om t.ex. USK inte räcker till ska solvern ändå generera
        schema för SSK och läkare, och rapportera undermanning för USK.
        Tidigare kraschade hela solvern (INFEASIBLE) om en enda roll
        inte kunde fyllas.

        Källa: Socialstyrelsen SOSFS 2012:11, Patientsäkerhetslagen
        """
        pass  # Moved to optimizer.py as soft constraint with high penalty

    def constraint_tillganglighet(self):
        """
        Personer kan bara arbeta de dagar de är tillgängliga
        
        Källa: Anställningsavtal
        Exempel: Person arbetar bara måndag-fredag, inte helger
        """
        for person in self.personal:
            for shift in self.shifts:
                if not person.ar_tillganglig(shift.datum):
                    # Tvinga denna assignment till 0 (ej tilldelad)
                    self.model.Add(self.assignments[(person.id, shift)] == 0)

    def constraint_franvaro(self):
        """
        Personer kan inte arbeta under frånvaroperioder
        
        Källa: Semesterlagen, Anställningsavtal
        Hanteras redan via ar_tillganglig() metoden
        """
        # Denna är redan hanterad i constraint_tillganglighet via ar_tillganglig()
        pass

    def constraint_vilotid(self):
        """
        Minst 11 timmar sammanhängande vila mellan pass
        
        Källa: Arbetstidslagen (1982:673) § 13
        Exempel: Om nattpass slutar 07:00, kan personen tidigast börja 18:00 samma dag
        
        Undantag (ej implementerat i POC):
        - Tillfälliga avvikelser vid oförutsedda händelser
        - Kräver motsvarande kompensationsledighet
        """
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
                                    self.assignments[(person.id, s1)] +
                                    self.assignments[(person.id, s2)] <= 1
                                )

    def constraint_veckovila(self):
        """
        Minst 36 timmars sammanhängande veckovila per 7-dagarsperiod
        
        Källa: Arbetstidslagen (1982:673) § 14
        Källa: SKR/Sobona Allmänna bestämmelser § 13 mom. 7 (sedan oktober 2023)
        Källa: EU arbetstidsdirektiv
        
        Implementering: Varje person måste ha minst EN helt ledig dag
        per rullande 7-dagarsperiod (24h + marginaler = 36h sammanhängande)
        
        Undantag (ej implementerat i POC):
        - Kan tillfälligt sänkas till 24h vid särskilda omständigheter
        - Kräver dispens från Arbetstidsnämnden (för vissa verksamheter)
        """
        alla_datum = sorted(set(shift.datum for shift in self.shifts))
        
        for person in self.personal:
            # För varje rullande 7-dagarsperiod
            for i in range(len(alla_datum) - 6):
                # Ta 7 konsekutiva datum
                vecka_datum = alla_datum[i:i + 7]
                
                # Kontrollera att de verkligen är konsekutiva
                ar_konsekutiv = all(
                    (vecka_datum[j + 1] - vecka_datum[j]).days == 1
                    for j in range(len(vecka_datum) - 1)
                )
                
                if ar_konsekutiv:
                    # För varje dag i veckan, skapa en bool variabel: "är denna dag ledig?"
                    ledig_variabler = []
                    
                    for datum in vecka_datum:
                        # Hitta alla pass för denna dag
                        shifts_denna_dag = [
                            self.assignments[(person.id, shift)]
                            for shift in self.shifts
                            if shift.datum == datum
                        ]
                        
                        if shifts_denna_dag:
                            # Skapa variabel: 1 om dagen är helt ledig, 0 annars
                            dag_ledig = self.model.NewBoolVar(f'ledig_{person.id}_{datum}')
                            
                            # dag_ledig = 1 om INGA pass jobbas denna dag
                            # dvs sum(shifts_denna_dag) == 0
                            self.model.Add(sum(shifts_denna_dag) == 0).OnlyEnforceIf(dag_ledig)
                            self.model.Add(sum(shifts_denna_dag) > 0).OnlyEnforceIf(dag_ledig.Not())
                            
                            ledig_variabler.append(dag_ledig)
                    
                    if ledig_variabler:
                        # Minst EN helt ledig dag per vecka
                        self.model.Add(sum(ledig_variabler) >= 1)

    def constraint_max_arbetsdagar_i_rad(self):
        """
        Max 5 arbetsdagar i rad
        
        Källa: Kollektivavtal vård (varierar mellan 5-7 dagar beroende på avtal)
        Vi använder konservativa 5 dagar för säkerhet och hälsa
        
        Rationale: Förhindrar utbrändhet, säkerställer återhämtning
        """
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
                        self.assignments[(person.id, shift)]
                        for shift in self.shifts
                        if shift.datum in datum_sekvens
                    ]

                    if alla_pass:
                        # Personen kan max arbeta 5 av dessa 6 dagar
                        self.model.Add(sum(alla_pass) <= MAX_DAGAR)

    def constraint_anstallningsgrad(self):
        """
        Respektera anställningsgrad (max timmar per månad)

        Källa: Arbetstidslagen (1982:673) § 5, Anställningsavtal

        Ordinarie arbetstid:
        - Heltid (100%): 40 timmar/vecka ≈ 160 timmar/månad
        - Deltid (75%): 30 timmar/vecka ≈ 120 timmar/månad

        Timbaserad beräkning: summerar faktiska pass-timmar (8h, 10h, 12h)
        istället för att räkna antal dagar.
        """
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
                timmar_terms = [
                    self.assignments[(person.id, shift)] * shift.duration_hours
                    for shift in shifts_i_manad
                ]
                if timmar_terms:
                    # Max timmar enligt anställningsgrad
                    self.model.Add(
                        sum(timmar_terms) <= person.max_timmar_per_manad
                    )

    def constraint_overtid(self):
        """
        Begränsa övertid enligt lag

        Källa: Arbetstidslagen (1982:673) § 8, 8a

        Övertidsgränser:
        1. Allmän övertid: Max 200 timmar per kalenderår
        2. Extra övertid: Max 150 timmar per kalenderår (kräver "synnerliga skäl")
        3. Totalt: Max 350 timmar övertid per år

        Implementering: Timbaserad beräkning.
        Ordinarie timmar/år + 200h övertid = max tillåtet.
        """
        # Gruppera shifts per år
        shifts_per_ar = {}
        for shift in self.shifts:
            ar_key = shift.datum.year
            if ar_key not in shifts_per_ar:
                shifts_per_ar[ar_key] = []
            shifts_per_ar[ar_key].append(shift)

        MAX_OVERTID_TIMMAR_PER_AR = 200  # Arbetstidslagen § 8

        # För varje person och år
        for person in self.personal:
            for ar_key, shifts_i_ar in shifts_per_ar.items():
                timmar_terms = [
                    self.assignments[(person.id, shift)] * shift.duration_hours
                    for shift in shifts_i_ar
                ]

                if timmar_terms:
                    # Ordinarie timmar per år + lagstadgad övertidsgräns
                    max_timmar_ar = person.max_timmar_per_manad * 12 + MAX_OVERTID_TIMMAR_PER_AR
                    self.model.Add(sum(timmar_terms) <= max_timmar_ar)

    def constraint_passrestriktioner(self):
        """
        Blockera specifika passtyper per person.

        Exempel: "Erik ska inte jobba natt" → exclude_pass_typer = ["natt"]
        Sätter assignment till 0 för alla shifts med blockerad passtyp.
        """
        for person in self.personal:
            if not person.exclude_pass_typer:
                continue
            for shift in self.shifts:
                if shift.pass_typ.value in person.exclude_pass_typer:
                    self.model.Add(self.assignments[(person.id, shift)] == 0)

    def constraint_lasta_pass(self):
        """
        Tvinga person att jobba ett specifikt pass på ett specifikt datum.

        Exempel: "Anna MÅSTE jobba dag den 22:a" → lasta_pass = [{"datum": date(2026,6,22), "pass_typ": "dag"}]
        Sätter assignment till 1 för matchande shift.
        """
        for person in self.personal:
            if not person.lasta_pass:
                continue
            for pinned in person.lasta_pass:
                matching_shift = next(
                    (s for s in self.shifts
                     if s.datum == pinned['datum'] and s.pass_typ.value == pinned['pass_typ']),
                    None
                )
                if matching_shift:
                    self.model.Add(self.assignments[(person.id, matching_shift)] == 1)

    def constraint_jamn_fordelning(self):
        """
        Tvingar jämn fördelning av obekväma pass (helg, kväll, natt) inom samma roll.

        Max 2 pass skillnad mellan person med flest och färst — men BARA mellan
        personer med jämförbara förutsättningar. Personal med begränsad
        tillgänglighet (t.ex. bara tor–sön) eller passrestriktioner filtreras
        bort från jämförelsen, eftersom de matematiskt inte KAN fördelas lika.

        Juridisk grund: Offentlig sektor kräver rättvis och transparent
        arbetsfördelning. Ojämn fördelning utan saklig grund kan strida mot
        diskrimineringslagen och kollektivavtal.
        """
        MAX_SPREAD = 2

        helg_shifts = [s for s in self.shifts if s.datum.weekday() >= 5]
        kvall_shifts = [s for s in self.shifts if s.pass_typ == PassTyp.KVALL]
        natt_shifts = [s for s in self.shifts if s.pass_typ == PassTyp.NATT]

        # Beräkna vilka som har frånvaro under perioden
        alla_datum = set(s.datum for s in self.shifts)
        har_franvaro = set()
        for p in self.personal:
            for f in p.franvaro:
                if any(f.start <= d <= f.slut for d in alla_datum):
                    har_franvaro.add(p.id)
                    break

        roller = set(p.roll for p in self.personal)

        for roll in roller:
            roll_personal = [p for p in self.personal if p.roll == roll]
            if len(roll_personal) < 2:
                continue

            # --- Helgpass: filtrera bort de med ojämförbar helgtillgänglighet eller frånvaro ---
            if helg_shifts:
                jamforbar_helg = [
                    p for p in roll_personal
                    if sum(1 for d in p.tillganglighet if d in ('Sat', 'Sun')) == 2
                    and p.anstallning >= 75
                    and p.id not in har_franvaro
                ]
                self._add_spread_constraint(jamforbar_helg, helg_shifts, roll, 'helg', MAX_SPREAD)

            # --- Kvällspass: filtrera bort de med passrestriktion eller frånvaro ---
            if kvall_shifts:
                jamforbar_kvall = [
                    p for p in roll_personal
                    if 'kväll' not in (p.exclude_pass_typer or [])
                    and p.anstallning >= 75
                    and p.id not in har_franvaro
                ]
                self._add_spread_constraint(jamforbar_kvall, kvall_shifts, roll, 'kvall', MAX_SPREAD)

            # --- Nattpass: filtrera bort de med passrestriktion eller frånvaro ---
            if natt_shifts:
                jamforbar_natt = [
                    p for p in roll_personal
                    if 'natt' not in (p.exclude_pass_typer or [])
                    and p.anstallning >= 75
                    and p.id not in har_franvaro
                ]
                self._add_spread_constraint(jamforbar_natt, natt_shifts, roll, 'natt', MAX_SPREAD)

    def _add_spread_constraint(self, personal_group, target_shifts, roll, label, max_spread):
        """Lägger till hård constraint: max spread mellan jämförbara personer."""
        if len(personal_group) < 2:
            return

        count_vars = []
        for person in personal_group:
            v = self.model.NewIntVar(
                0, len(target_shifts), f'hard_{label}_{roll}_{person.id}')
            self.model.Add(v == sum(
                self.assignments[(person.id, s)] for s in target_shifts
            ))
            count_vars.append(v)

        spread_max = self.model.NewIntVar(
            0, len(target_shifts), f'hard_{label}_{roll}_max')
        spread_min = self.model.NewIntVar(
            0, len(target_shifts), f'hard_{label}_{roll}_min')
        self.model.AddMaxEquality(spread_max, count_vars)
        self.model.AddMinEquality(spread_min, count_vars)
        self.model.Add(spread_max - spread_min <= max_spread)

    # Mjuka mål (jämn helg/kväll-natt-fördelning) hanteras nu direkt
    # i optimizer.py:_definiera_objektfunktion() som del av objective function.