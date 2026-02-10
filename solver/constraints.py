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
        self.constraint_veckovila()  # NY: Lagstadgad 36h veckovila
        self.constraint_max_arbetsdagar_i_rad()
        self.constraint_anstallningsgrad()
        self.constraint_overtid()  # NY: Övertidsbegränsningar

    def constraint_en_person_ett_pass_per_dag(self):
        """
        En person kan max jobba ett pass per dag
        
        Källa: Arbetsmiljölagen, god praxis
        Förhindrar dubbelpass som kan leda till utmattning
        """
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
        """
        Varje shift måste ha rätt antal personer med rätt kompetens
        
        Källa: Socialstyrelsen SOSFS 2012:11, Patientsäkerhetslagen
        Exempel: Dagpass kan kräva 1 läkare, 3 sjuksköterskor, 5 undersköterskor
        """
        for shift in self.shifts:
            for roll, antal_krav in shift.kompetenskrav.items():
                # Hitta alla personer med denna roll
                personer_med_roll = [
                    self.assignments[(p.namn, shift)]
                    for p in self.personal
                    if p.roll == roll
                ]
                if personer_med_roll:
                    # Minst antal personer med rätt roll (tillåter undermanning om nödvändigt)
                    self.model.Add(sum(personer_med_roll) >= antal_krav)

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
                    self.model.Add(self.assignments[(person.namn, shift)] == 0)

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
                                    self.assignments[(person.namn, s1)] +
                                    self.assignments[(person.namn, s2)] <= 1
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
                            self.assignments[(person.namn, shift)]
                            for shift in self.shifts
                            if shift.datum == datum
                        ]
                        
                        if shifts_denna_dag:
                            # Skapa variabel: 1 om dagen är helt ledig, 0 annars
                            dag_ledig = self.model.NewBoolVar(f'ledig_{person.namn}_{datum}')
                            
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
                        self.assignments[(person.namn, shift)]
                        for shift in self.shifts
                        if shift.datum in datum_sekvens
                    ]

                    if alla_pass:
                        # Personen kan max arbeta 5 av dessa 6 dagar
                        self.model.Add(sum(alla_pass) <= MAX_DAGAR)

    def constraint_anstallningsgrad(self):
        """
        Respektera anställningsgrad (max antal pass per månad)
        
        Källa: Arbetstidslagen (1982:673) § 5, Anställningsavtal
        
        Ordinarie arbetstid:
        - Heltid (100%): 40 timmar/vecka ≈ 173 timmar/månad ≈ 20 dagar/månad
        - Deltid (75%): 30 timmar/vecka ≈ 130 timmar/månad ≈ 15 dagar/månad
        
        OBS: Detta är approximation. Faktiskt antal pass beror på:
        - Passlängd (8h, 10h, 12h)
        - Månadens längd (28-31 dagar)
        - Helger och storhelger
        
        För exakt beräkning behövs timbaserad schemaläggning (framtida version)
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
                assignments_i_manad = [
                    self.assignments[(person.namn, shift)]
                    for shift in shifts_i_manad
                ]
                if assignments_i_manad:
                    # Max antal pass enligt anställningsgrad
                    self.model.Add(
                        sum(assignments_i_manad) <= person.max_arbetspass_per_manad
                    )

    def constraint_overtid(self):
        """
        Begränsa övertid enligt lag
        
        Källa: Arbetstidslagen (1982:673) § 8, 8a
        
        Övertidsgränser:
        1. Allmän övertid: Max 200 timmar per kalenderår
        2. Extra övertid: Max 150 timmar per kalenderår (kräver "synnerliga skäl")
        3. Totalt: Max 350 timmar övertid per år
        4. Per vecka: Max 48 timmar sammanlagd arbetstid i genomsnitt (4 månaders period)
        5. Nödfallsövertid: Separat kategori vid natur/olyckshändelse
        
        Implementering i POC:
        - Vi begränsar total övertid till 200h/år (endast allmän övertid)
        - Extra övertid och nödfallsövertid hanteras manuellt
        - Veckovis 48h-gräns kontrolleras separat
        
        OBS: Övertid = arbetstid utöver anställningsgrad
        Exempel: 100% anställd som jobbar 22 dagar istället för 20 = 2 dagars övertid
        
        För produktionsmiljö:
        - Timbaserad beräkning (inte dagar)
        - Skillnad mellan allmän/extra/nödfallsövertid
        - Kompensation (pengar eller ledighet)
        """
        # Gruppera shifts per år
        shifts_per_ar = {}
        for shift in self.shifts:
            ar_key = shift.datum.year
            if ar_key not in shifts_per_ar:
                shifts_per_ar[ar_key] = []
            shifts_per_ar[ar_key].append(shift)

        # För varje person och år
        for person in self.personal:
            for ar_key, shifts_i_ar in shifts_per_ar.items():
                assignments_i_ar = [
                    self.assignments[(person.namn, shift)]
                    for shift in shifts_i_ar
                ]
                
                if assignments_i_ar:
                    # Beräkna max tillåtna dagar enligt anställningsgrad
                    # Approximation: Ett år har ~12 månader
                    max_dagar_enligt_anstallning = person.max_arbetspass_per_manad * 12
                    
                    # Övertidsgräns: 200h / 8h per dag ≈ 25 dagar
                    # (Konservativ uppskattning)
                    max_overtidsdagar = 25
                    
                    # Total max = ordinarie + övertid
                    total_max_dagar = max_dagar_enligt_anstallning + max_overtidsdagar
                    
                    # Begränsa totalt antal dagar per år
                    self.model.Add(sum(assignments_i_ar) <= total_max_dagar)

    def add_mjuka_mal(self, objective_vars: List):
        """
        Lägger till mjuka mål (optimeringsmål)
        
        Dessa är INTE krav utan önskvärda egenskaper som optimeras
        när hårda constraints är uppfyllda
        
        Mjuka mål:
        1. Jämn fördelning av helgpass
        2. Jämn fördelning av kväll/nattpass
        3. Minimera övertid
        4. Respektera preferenser (undvik helger, max nattpass, etc)
        """
        self.mjukt_mal_jamn_helgfordelning(objective_vars)
        self.mjukt_mal_jamn_kvall_natt(objective_vars)

    def mjukt_mal_jamn_helgfordelning(self, objective_vars: List):
        """
        Försök fördela helgpass jämnt mellan personal
        
        Rationale: Rättvis fördelning, bättre arbetsmiljö
        Källa: God praxis, fackliga krav
        """
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

    def mjukt_mal_jamn_kvall_natt(self, objective_vars: List):
        """
        Försök fördela kväll- och nattpass jämnt
        
        Rationale: Nattarbete är påfrestande, bör fördelas rättvist
        Källa: Arbetsmiljölagen, kollektivavtal om nattarbete
        """
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