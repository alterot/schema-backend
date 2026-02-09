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

## Testning

Se `test_example.json` för ett komplett exempel på input-data.
