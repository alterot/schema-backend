from flask import Flask, request, jsonify
from flask_cors import CORS
from typing import Dict, Any
import traceback
from datetime import date, timedelta

from models import Person, Shift
from solver import SchemaOptimizer
from utils import validate_input, ValidationError, calculate_all_metrics
from data import get_personal, get_bemanningsbehov, get_regler, get_avdelning, generate_shifts_for_period

app = Flask(__name__)

# Konfigurera CORS för att tillåta React frontend
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:3000", "http://localhost:5173"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})


@app.route('/api/health', methods=['GET'])
def health_check():
    """Hälsokontroll för att verifiera att API:et är igång"""
    return jsonify({
        'status': 'ok',
        'service': 'Schema-assistent Backend',
        'version': '1.0.0'
    })


@app.route('/api/generate', methods=['POST'])
def generate_schedule():
    """
    Huvudendpoint för schemagenerering.

    Input (JSON):
    {
        "personal": [...],
        "behov": [...],
        "config": {...}
    }

    Output (JSON):
    {
        "schema": [...],
        "konflikter": [...],
        "statistik": {...},
        "metrics": {
            "coverage_percent": float,
            "overtime_hours": float,
            "rule_violations": int,
            "cost_kr": float,
            "quality_score": int
        }
    }
    """
    try:
        # Steg 1: Hämta och validera input
        data = request.get_json()

        if not data:
            return jsonify({
                'error': 'Ingen data mottagen',
                'detaljer': 'Request body måste innehålla JSON-data'
            }), 400

        # Validera input-strukturen
        try:
            validate_input(data)
        except ValidationError as e:
            return jsonify({
                'error': 'Valideringsfel',
                'detaljer': str(e)
            }), 400

        # Steg 2: Konvertera till datamodeller
        personal = [Person.from_dict(p) for p in data['personal']]
        shifts = [Shift.from_dict(s) for s in data['behov']]

        # Steg 3: Validera att vi har data att arbeta med
        if not personal:
            return jsonify({
                'error': 'Ingen personal angiven',
                'detaljer': 'Det måste finnas minst en person i listan'
            }), 400

        if not shifts:
            return jsonify({
                'error': 'Inga pass angivna',
                'detaljer': 'Det måste finnas minst ett pass att schemalägga'
            }), 400

        # Steg 4: Kör optimering
        optimizer = SchemaOptimizer(personal, shifts)
        schedule = optimizer.optimera()

        # Steg 5: Beräkna metrics
        metrics = calculate_all_metrics(
            schema_rader=schedule.rader,
            konflikter=schedule.konflikter,
            shifts=shifts,
            personal=personal
        )

        # Steg 6: Returnera resultat med metrics
        result = schedule.to_dict()
        result['metrics'] = metrics
        return jsonify(result), 200

    except ValidationError as e:
        # Specifika valideringsfel
        return jsonify({
            'error': 'Valideringsfel',
            'detaljer': str(e)
        }), 400

    except Exception as e:
        # Oväntade fel
        app.logger.error(f'Oväntat fel vid schemagenerering: {str(e)}')
        app.logger.error(traceback.format_exc())

        return jsonify({
            'error': 'Internt serverfel',
            'detaljer': 'Ett oväntat fel uppstod vid schemagenerering',
            'teknisk_info': str(e) if app.debug else None
        }), 500


@app.route('/api/generate-realistic', methods=['POST'])
def generate_realistic_schedule():
    """
    Genererar schema med realistisk sjukhusdata.

    Input (JSON):
    {
        "start_date": "2025-04-01",  // Optional, default: idag
        "end_date": "2025-04-30",    // Optional, default: 30 dagar fram
        "scenario": "normal_april"   // Optional testscenario
    }

    Output (JSON):
    {
        "schema": [...],
        "konflikter": [...],
        "statistik": {...},
        "metrics": {...},
        "data_source": "realistic_hospital_data"
    }
    """
    try:
        data = request.get_json() or {}

        # Hantera datum
        today = date.today()
        start_str = data.get('start_date')
        end_str = data.get('end_date')

        if start_str:
            start_date = date.fromisoformat(start_str)
        else:
            start_date = today

        if end_str:
            end_date = date.fromisoformat(end_str)
        else:
            end_date = start_date + timedelta(days=30)

        # Hamta personal fran realistisk data
        personal_data = get_personal()

        # Hamta avdelning
        avdelning_info = get_avdelning()
        avdelning_namn = avdelning_info['namn']

        # Generera shifts for perioden
        shifts_data = generate_shifts_for_period(start_date, end_date, avdelning_namn)

        # Konvertera till datamodeller
        personal = [Person.from_dict(p) for p in personal_data]
        shifts = [Shift.from_dict(s) for s in shifts_data]

        # Validera att vi har data att arbeta med
        if not personal:
            return jsonify({
                'error': 'Ingen personal i data',
                'detaljer': 'Kontrollera realistic_hospital_data.json'
            }), 400

        if not shifts:
            return jsonify({
                'error': 'Inga pass genererade',
                'detaljer': 'Kontrollera datum-intervallet'
            }), 400

        # Kor optimering
        optimizer = SchemaOptimizer(personal, shifts)
        schedule = optimizer.optimera()

        # Berakna metrics
        metrics = calculate_all_metrics(
            schema_rader=schedule.rader,
            konflikter=schedule.konflikter,
            shifts=shifts,
            personal=personal
        )

        # Returnera resultat
        result = schedule.to_dict()
        result['metrics'] = metrics
        result['data_source'] = 'realistic_hospital_data'
        result['period'] = {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        }
        result['avdelning'] = avdelning_info

        return jsonify(result), 200

    except ValueError as e:
        return jsonify({
            'error': 'Ogiltigt datum',
            'detaljer': str(e)
        }), 400

    except Exception as e:
        app.logger.error(f'Oväntat fel vid realistisk schemagenerering: {str(e)}')
        app.logger.error(traceback.format_exc())

        return jsonify({
            'error': 'Internt serverfel',
            'detaljer': 'Ett oväntat fel uppstod vid schemagenerering',
            'teknisk_info': str(e) if app.debug else None
        }), 500


@app.route('/api/data/personal', methods=['GET'])
def get_personal_endpoint():
    """Returnerar listan med personal fran realistisk data."""
    try:
        personal = get_personal()
        return jsonify({
            'personal': personal,
            'antal': len(personal)
        }), 200
    except Exception as e:
        app.logger.error(f'Fel vid hamtning av personal: {str(e)}')
        return jsonify({'error': 'Kunde inte hamta personal'}), 500


@app.route('/api/data/bemanningsbehov', methods=['GET'])
def get_bemanningsbehov_endpoint():
    """Returnerar bemanningsbehov for vardag och helg."""
    try:
        vardag = get_bemanningsbehov(is_weekend=False)
        helg = get_bemanningsbehov(is_weekend=True)
        return jsonify({
            'vardag': vardag,
            'helg': helg
        }), 200
    except Exception as e:
        app.logger.error(f'Fel vid hamtning av bemanningsbehov: {str(e)}')
        return jsonify({'error': 'Kunde inte hamta bemanningsbehov'}), 500


@app.route('/api/data/regler', methods=['GET'])
def get_regler_endpoint():
    """Returnerar regler for schemalagning."""
    try:
        regler = get_regler()
        return jsonify(regler), 200
    except Exception as e:
        app.logger.error(f'Fel vid hamtning av regler: {str(e)}')
        return jsonify({'error': 'Kunde inte hamta regler'}), 500


@app.route('/api/validate', methods=['POST'])
def validate_input_endpoint():
    """
    Endpoint för att validera input utan att generera schema.
    Användbart för frontend-validering.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'valid': False,
                'error': 'Ingen data mottagen'
            }), 400

        # Försök validera
        validate_input(data)

        # Om vi kommer hit är datan giltig
        return jsonify({
            'valid': True,
            'message': 'Input är giltig',
            'statistik': {
                'antal_personal': len(data.get('personal', [])),
                'antal_pass': len(data.get('behov', []))
            }
        }), 200

    except ValidationError as e:
        return jsonify({
            'valid': False,
            'error': str(e)
        }), 400

    except Exception as e:
        app.logger.error(f'Fel vid validering: {str(e)}')
        return jsonify({
            'valid': False,
            'error': 'Oväntat fel vid validering'
        }), 500


@app.route('/api/schedule/<period>', methods=['GET'])
def get_schedule(period: str):
    """
    Tool endpoint: Hämta befintligt schema för en period.

    Args:
        period: YYYY-MM format (t.ex. "2025-04")

    Returns:
        {
            "schema": [...],
            "metrics": {...}
        }
    """
    try:
        # Validera period-format
        try:
            year, month = period.split('-')
            year = int(year)
            month = int(month)
            if not (1 <= month <= 12):
                raise ValueError()
        except (ValueError, AttributeError):
            return jsonify({
                'error': 'Ogiltigt periodformat',
                'detaljer': f"Period '{period}' är ogiltig. Använd format YYYY-MM (t.ex. '2025-04')"
            }), 400

        # POC: Returnera mock-data
        # I produktion skulle detta hämta från databas
        return jsonify({
            'schema': [],
            'metrics': {
                'coverage_percent': 0.0,
                'overtime_hours': 0.0,
                'rule_violations': 0,
                'cost_kr': 0.0,
                'quality_score': 0
            },
            'message': f'Inget schema hittades för period {period} (POC-läge)'
        }), 200

    except Exception as e:
        app.logger.error(f'Fel vid hämtning av schema: {str(e)}')
        return jsonify({
            'error': 'Internt serverfel',
            'detaljer': 'Kunde inte hämta schema'
        }), 500


@app.route('/api/propose', methods=['POST'])
def propose_changes():
    """
    Tool endpoint: Föreslå schemaändringar baserat på problem.

    Input:
        {
            "problem": "beskrivning av problem"
        }

    Output:
        {
            "proposals": [lista med lösningar],
            "reasoning": "..."
        }
    """
    try:
        data = request.get_json()

        if not data or 'problem' not in data:
            return jsonify({
                'error': 'Saknar problem-beskrivning',
                'detaljer': 'Request body måste innehålla "problem"-fält'
            }), 400

        problem = data['problem']

        # POC: Returnera mock-förslag
        # I produktion skulle detta använda AI/solver för att generera förslag
        return jsonify({
            'proposals': [
                {
                    'id': 1,
                    'beskrivning': 'Flytta personal från pass med övermanning',
                    'paverkan': 'Reducerar övertid med ~10h',
                    'kostnad_kr': 0
                },
                {
                    'id': 2,
                    'beskrivning': 'Schemalägg vikarie för kritiska pass',
                    'paverkan': 'Ökar coverage till 100%',
                    'kostnad_kr': 8400
                }
            ],
            'reasoning': f'Baserat på problem "{problem}", identifierades 2 möjliga lösningar. '
                        'Förslag 1 omfördelar befintlig personal, förslag 2 använder vikarier.',
            'problem_analyzed': problem
        }), 200

    except Exception as e:
        app.logger.error(f'Fel vid förslag av ändringar: {str(e)}')
        return jsonify({
            'error': 'Internt serverfel',
            'detaljer': 'Kunde inte generera förslag'
        }), 500


@app.route('/api/simulate', methods=['POST'])
def simulate_impact():
    """
    Tool endpoint: Simulera konsekvenser av schemaändringar.

    Input:
        {
            "changes": [lista med ändringar]
        }

    Output:
        {
            "metrics_before": {...},
            "metrics_after": {...},
            "impact": "..."
        }
    """
    try:
        data = request.get_json()

        if not data or 'changes' not in data:
            return jsonify({
                'error': 'Saknar ändringar',
                'detaljer': 'Request body måste innehålla "changes"-fält'
            }), 400

        changes = data['changes']

        # POC: Returnera mock-simulering
        # I produktion skulle detta köra solver med ändringarna och jämföra metrics
        metrics_before = {
            'coverage_percent': 92.5,
            'overtime_hours': 24.0,
            'rule_violations': 3,
            'cost_kr': 156000.0,
            'quality_score': 76
        }

        metrics_after = {
            'coverage_percent': 98.0,
            'overtime_hours': 16.0,
            'rule_violations': 1,
            'cost_kr': 152000.0,
            'quality_score': 88
        }

        return jsonify({
            'metrics_before': metrics_before,
            'metrics_after': metrics_after,
            'impact': 'Föreslagna ändringar förbättrar coverage med 5.5%, '
                     'reducerar övertid med 8h, minskar regelbrott från 3 till 1, '
                     'och sparar 4000 kr samtidigt som quality score ökar från 76 till 88.',
            'changes_count': len(changes) if isinstance(changes, list) else 0
        }), 200

    except Exception as e:
        app.logger.error(f'Fel vid simulering: {str(e)}')
        return jsonify({
            'error': 'Internt serverfel',
            'detaljer': 'Kunde inte simulera ändringar'
        }), 500


@app.route('/api/apply', methods=['POST'])
def apply_changes():
    """
    Tool endpoint: Applicera godkända schemaändringar.

    Input:
        {
            "schema": {...},
            "confirmed": bool
        }

    Output:
        {
            "success": bool,
            "message": "..."
        }
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'error': 'Ingen data mottagen',
                'detaljer': 'Request body måste innehålla JSON-data'
            }), 400

        if 'confirmed' not in data:
            return jsonify({
                'error': 'Saknar bekräftelse',
                'detaljer': 'Request body måste innehålla "confirmed"-fält'
            }), 400

        if not data['confirmed']:
            return jsonify({
                'success': False,
                'message': 'Ändringar ej bekräftade - ingen action utförd'
            }), 200

        if 'schema' not in data:
            return jsonify({
                'error': 'Saknar schema',
                'detaljer': 'Request body måste innehålla "schema"-fält när confirmed=true'
            }), 400

        schema = data['schema']

        # POC: Simulera att ändringarna appliceras
        # I produktion skulle detta spara till databas
        return jsonify({
            'success': True,
            'message': 'Schema uppdaterat framgångsrikt (POC-läge - ingen databas)',
            'timestamp': '2025-04-15T10:30:00Z',
            'changes_applied': True
        }), 200

    except Exception as e:
        app.logger.error(f'Fel vid applicering av ändringar: {str(e)}')
        return jsonify({
            'error': 'Internt serverfel',
            'detaljer': 'Kunde inte applicera ändringar'
        }), 500


@app.errorhandler(404)
def not_found(error):
    """Hanterare för 404-fel"""
    return jsonify({
        'error': 'Endpoint hittades inte',
        'detaljer': 'Kontrollera att du använder rätt URL'
    }), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Hanterare för 405-fel (felaktig HTTP-metod)"""
    return jsonify({
        'error': 'HTTP-metod inte tillåten',
        'detaljer': 'Kontrollera att du använder rätt HTTP-metod (GET/POST)'
    }), 405


@app.errorhandler(500)
def internal_error(error):
    """Hanterare för 500-fel"""
    app.logger.error(f'Internt serverfel: {str(error)}')
    return jsonify({
        'error': 'Internt serverfel',
        'detaljer': 'Ett oväntat fel uppstod på servern'
    }), 500


if __name__ == '__main__':
    # Utvecklingsserver
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True
    )
