# Schema-assistent Backend

Backend för schemaläggningsassistent för vårdavdelningar. Bygger på Flask och OR-Tools constraint solver.

## Arkitektur

- **Flask API**: REST API med CORS för React frontend
- **OR-Tools**: Constraint programming solver för optimal schemagenerering
- **Datamodeller**: Type-safe dataklasser med validering

## Filstruktur

```
backend/
├── app.py                  # Flask API med endpoints
├── models/
│   ├── person.py          # Person och Frånvaro
│   ├── shift.py           # Shift och PassTyp
│   └── schedule.py        # Schedule, SchemaRad, Konflikt
├── solver/
│   ├── constraints.py     # Constraint-definitioner
│   └── optimizer.py       # OR-Tools solver
├── utils/
│   └── validators.py      # Input validering
└── requirements.txt       # Python dependencies
```

## Installation

1. Skapa virtuell miljö:
```bash
python -m venv venv
```

2. Aktivera virtuell miljö:
```bash
# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

3. Installera dependencies:
```bash
pip install -r requirements.txt
```

## Kör servern

```bash
python app.py
```

Servern startar på `http://localhost:5000`

## API Endpoints

### POST /api/generate

Genererar schema baserat på personal och behov.

**Request:**
```json
{
  "personal": [
    {
      "namn": "Anna Berg",
      "roll": "sjukskoterska",
      "anstallning": 100,
      "tillganglighet": ["Mon", "Tue", "Wed", "Thu", "Fri"],
      "franvaro": [
        {
          "start": "2025-04-10",
          "slut": "2025-04-20",
          "typ": "semester"
        }
      ]
    }
  ],
  "behov": [
    {
      "datum": "2025-04-01",
      "pass": "dag",
      "avdelning": "3B",
      "kompetenskrav": {
        "sjukskoterska": 2,
        "underskoterska": 3
      }
    }
  ],
  "config": {
    "period": "2025-04"
  }
}
```

**Response:**
```json
{
  "schema": [
    {
      "datum": "2025-04-01",
      "pass": "dag",
      "avdelning": "3B",
      "personal": ["Anna Berg", "Bengt Svensson"]
    }
  ],
  "konflikter": [],
  "statistik": {
    "totalt_antal_pass": 30,
    "antal_konflikter": 0,
    "pass_per_person": {
      "Anna Berg": {
        "totalt": 20,
        "dag": 15,
        "kväll": 3,
        "natt": 2,
        "helger": 4
      }
    }
  }
}
```

### POST /api/validate

Validerar input utan att generera schema.

**Response:**
```json
{
  "valid": true,
  "message": "Input är giltig",
  "statistik": {
    "antal_personal": 5,
    "antal_pass": 30
  }
}
```

### GET /api/health

Hälsokontroll.

**Response:**
```json
{
  "status": "ok",
  "service": "Schema-assistent Backend",
  "version": "1.0.0"
}
```

## Constraints

### Hårda constraints (måste uppfyllas)

1. **Vilotid**: Minst 11 timmar mellan pass
2. **Max arbetsdagar**: Max 5 arbetsdagar i rad
3. **Kompetenskrav**: Varje pass måste ha rätt antal personer med rätt roll
4. **Anställningsgrad**: 75% ≈ 15 dagar/månad, 100% ≈ 20 dagar/månad
5. **Tillgänglighet**: Respektera vilka veckodagar person kan jobba
6. **Frånvaro**: Hårt bokad ledighet (semester, sjukdom)

### Mjuka mål (optimeras)

1. **Jämn helgfördelning**: Fördela helgpass rättvist
2. **Jämn kväll/nattfördelning**: Fördela obekväma pass rättvist
3. **Minimera övertid**: Håll inom anställningsgrad

## Konflikter

Om ingen perfekt lösning hittas returneras konflikter:

- **undermanning**: För få personer för ett pass
- **overbemanning**: Fler personer än nödvändigt (varning)
- **obalanserad_helgfordelning**: Ojämn fördelning av helgpass
- **obalanserad_kvall_natt**: Ojämn fördelning av kväll/nattpass
- **inga_losningar**: Ingen giltig lösning (för många constraints)
- **otillracklig_kapacitet**: För få personer totalt
- **otillracklig_kompetens**: För få med rätt roll
- **franvaro_konflikt**: Frånvaro orsakar bemanningsproblem

Allvarlighetsgrad: 1 = varning, 2 = allvarlig, 3 = kritisk

## Utveckling

### Lägga till nya constraints

1. Definiera constraint i `solver/constraints.py`
2. Anropa från `add_harda_constraints()` eller `add_mjuka_mal()`

### Lägga till nya valideringar

Uppdatera `utils/validators.py` med nya valideringsregler.

## Audit Log (Supabase)

Varje schemagenerering loggas till tabellen `audit_log` i Supabase. Kräver att `SUPABASE_URL` och `SUPABASE_KEY` är satta i `.env`. Om de saknas körs appen utan audit-loggning.

### Kolumner

| Kolumn | Typ | Beskrivning |
|--------|-----|-------------|
| `period` | text | Vilken månad schemat gäller, t.ex. `"2026-03"` |
| `user_input` | text | Användarens fritext till AI-chatten, t.ex. *"Lisa är sjuk 10-14 mars"* |
| `ai_reasoning` | text | AI-agentens resonemang och analys av instruktionen |
| `personal_overrides` | jsonb | De ändringar AI-agenten skickade till solvern. Tom `[]` vid ren generering utan modifieringar. Exempel: `[{"namn": "Lisa", "add_franvaro": {"start": "2026-03-10", "slut": "2026-03-14"}}]` |
| `schedule_data` | jsonb | Hela schemat: en array med `{datum, pass, avdelning, personal: [person-ID:n]}`. Koppla med `personal_lookup` nedan för att se namn. |
| `personal_lookup` | jsonb | Mappning från person-ID till namn och roll: `{"1": {"namn": "Anna Lindqvist", "roll": "sjukskoterska"}, ...}`. Nyckel for att tyda ID:n i `schedule_data`. |
| `metrics` | jsonb | `{coverage_percent, overtime_hours, rule_violations, cost_kr, quality_score}` |
| `konflikter` | jsonb | Lista med konflikter: `{datum, pass_typ, typ, beskrivning, allvarlighetsgrad}` |
| `solver_status` | text | `"OPTIMAL"` (lösning hittad) eller `"INFEASIBLE"` (inga lösningar) |
| `antal_personal` | int | Antal personer i beräkningen (inkl. eventuella vikarier) |
| `duration_ms` | int | Tid i millisekunder som solvern tog |
| `created_at` | timestamp | Automatisk tidsstämpel (sätts av Supabase) |

### Setup i Supabase

Skapa tabellen via SQL Editor:

```sql
CREATE TABLE audit_log (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  created_at timestamptz DEFAULT now(),
  period text NOT NULL,
  user_input text,
  ai_reasoning text,
  personal_overrides jsonb DEFAULT '[]',
  schedule_data jsonb DEFAULT '[]',
  personal_lookup jsonb DEFAULT '{}',
  metrics jsonb DEFAULT '{}',
  konflikter jsonb DEFAULT '[]',
  solver_status text,
  antal_personal int,
  duration_ms int
);
```

### Exempelquery: visa schema med namn

```sql
SELECT
  period,
  created_at,
  solver_status,
  metrics->>'coverage_percent' AS coverage,
  metrics->>'quality_score' AS quality,
  duration_ms,
  personal_lookup
FROM audit_log
ORDER BY created_at DESC
LIMIT 10;
```

### Noteringar

- `personal_overrides` fylls bara när AI-agenten aktivt modifierar personal (t.ex. lägger till frånvaro, vikarier, eller ändrar tillgänglighet). Vid en ren schemagenerering utan modifieringar är den tom `[]` -- det är korrekt beteende.
- `schedule_data` innehåller person-ID:n (heltal) i `personal`-fältet, inte namn. Använd `personal_lookup` för att slå upp vem varje ID är.
- Om `SUPABASE_URL`/`SUPABASE_KEY` inte är konfigurerade loggas en varning vid uppstart, men appen fungerar normalt utan audit-loggning.

## Testning

Se `test_example.json` för ett komplett exempel på input-data.
