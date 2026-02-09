"""
Test-script för att verifiera att API:et fungerar korrekt.
Kör detta efter att ha startat Flask-servern (python app.py).
"""

import requests
import json
from pprint import pprint

BASE_URL = 'http://localhost:5000'


def test_health_check():
    """Testar halsokontrollen"""
    print("\n" + "="*60)
    print("TEST 1: Halsokontroll")
    print("="*60)

    response = requests.get(f'{BASE_URL}/api/health')

    print(f"Status: {response.status_code}")
    pprint(response.json())

    assert response.status_code == 200
    assert response.json()['status'] == 'ok'
    print("[OK] Halsokontroll lyckades")


def test_validate():
    """Testar validering av input"""
    print("\n" + "="*60)
    print("TEST 2: Validering")
    print("="*60)

    # Las testdata
    with open('test_example.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    response = requests.post(
        f'{BASE_URL}/api/validate',
        json=data,
        headers={'Content-Type': 'application/json'}
    )

    print(f"Status: {response.status_code}")
    pprint(response.json())

    assert response.status_code == 200
    assert response.json()['valid'] == True
    print("[OK] Validering lyckades")


def test_generate_schedule():
    """Testar schemagenerering"""
    print("\n" + "="*60)
    print("TEST 3: Schemagenerering")
    print("="*60)

    # Las testdata
    with open('test_example.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    response = requests.post(
        f'{BASE_URL}/api/generate',
        json=data,
        headers={'Content-Type': 'application/json'}
    )

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()

        print(f"\nGenererade {len(result['schema'])} schemarader")
        print(f"Antal konflikter: {len(result['konflikter'])}")

        if result['konflikter']:
            print("\nKonflikter:")
            for konflikt in result['konflikter']:
                print(f"  - {konflikt['typ']}: {konflikt['beskrivning']}")

        print("\nStatistik:")
        pprint(result['statistik'])

        print("\nMetrics:")
        if 'metrics' in result:
            metrics = result['metrics']
            print(f"  Coverage: {metrics['coverage_percent']}%")
            print(f"  Övertid: {metrics['overtime_hours']} timmar")
            print(f"  Regelbrott: {metrics['rule_violations']}")
            print(f"  Kostnad: {metrics['cost_kr']:,.2f} kr")
            print(f"  Kvalitetspoäng: {metrics['quality_score']}/100")
        else:
            print("  (Inga metrics tillgängliga)")

        print("\nExempel på schemarader:")
        for rad in result['schema'][:5]:
            print(f"  {rad['datum']} {rad['pass']}: {', '.join(rad['personal'])}")

        print("[OK] Schemagenerering lyckades")
    else:
        print(f"[ERROR] Fel: {response.status_code}")
        pprint(response.json())


def test_invalid_input():
    """Testar felhantering med ogiltig input"""
    print("\n" + "="*60)
    print("TEST 4: Felhantering")
    print("="*60)

    # Ogiltig data (saknar personal)
    invalid_data = {
        "personal": [],
        "behov": [],
        "config": {"period": "2025-04"}
    }

    response = requests.post(
        f'{BASE_URL}/api/generate',
        json=invalid_data,
        headers={'Content-Type': 'application/json'}
    )

    print(f"Status: {response.status_code}")
    pprint(response.json())

    assert response.status_code == 400
    print("[OK] Felhantering fungerar korrekt")


def test_data_personal():
    """Testar hamtning av personal fran realistisk data"""
    print("\n" + "="*60)
    print("TEST 5: Hamta Personal")
    print("="*60)

    response = requests.get(f'{BASE_URL}/api/data/personal')

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print(f"Antal personal: {result['antal']}")
        print("\nPersonal:")
        for person in result['personal'][:5]:
            print(f"  - {person['namn']} ({person['roll']})")
        if result['antal'] > 5:
            print(f"  ... och {result['antal'] - 5} till")

        # Verifiera att lakare finns med
        roller = set(p['roll'] for p in result['personal'])
        print(f"\nRoller: {roller}")
        assert 'lakare' in roller, "lakare saknas i personal-datan"
        assert 'sjukskoterska' in roller
        assert 'underskoterska' in roller

        print("[OK] Personal-hamtning lyckades")
    else:
        print(f"[ERROR] Fel: {response.status_code}")
        pprint(response.json())


def test_data_bemanningsbehov():
    """Testar hamtning av bemanningsbehov"""
    print("\n" + "="*60)
    print("TEST 6: Hamta Bemanningsbehov")
    print("="*60)

    response = requests.get(f'{BASE_URL}/api/data/bemanningsbehov')

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("\nVardag:")
        pprint(result['vardag'])
        print("\nHelg:")
        pprint(result['helg'])

        # Verifiera lakare finns i behoven
        assert 'lakare' in result['vardag']['dag'], "lakare saknas i vardagsbehov"
        print("[OK] Bemanningsbehov-hamtning lyckades")
    else:
        print(f"[ERROR] Fel: {response.status_code}")
        pprint(response.json())


def test_data_regler():
    """Testar hamtning av schemalagningsregler"""
    print("\n" + "="*60)
    print("TEST 7: Hamta Regler")
    print("="*60)

    response = requests.get(f'{BASE_URL}/api/data/regler')

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()
        print("\nRegler:")
        pprint(result)

        assert 'vilotid_timmar' in result
        assert 'max_dagar_i_rad' in result
        assert 'timloner' in result
        print("[OK] Regler-hamtning lyckades")
    else:
        print(f"[ERROR] Fel: {response.status_code}")
        pprint(response.json())


def test_generate_realistic():
    """Testar schemagenerering med realistisk sjukhusdata"""
    print("\n" + "="*60)
    print("TEST 8: Schemagenerering med Realistisk Data")
    print("="*60)

    # Generera for en kortare period (7 dagar) for snabbare test
    response = requests.post(
        f'{BASE_URL}/api/generate-realistic',
        json={
            "start_date": "2025-04-01",
            "end_date": "2025-04-07"
        },
        headers={'Content-Type': 'application/json'}
    )

    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        result = response.json()

        print(f"\nGenererade {len(result['schema'])} schemarader")
        print(f"Antal konflikter: {len(result['konflikter'])}")
        print(f"Data source: {result.get('data_source', 'N/A')}")
        print(f"Period: {result.get('period', {})}")

        if result['konflikter']:
            print("\nKonflikter:")
            for konflikt in result['konflikter'][:5]:
                print(f"  - {konflikt['typ']}: {konflikt['beskrivning']}")
            if len(result['konflikter']) > 5:
                print(f"  ... och {len(result['konflikter']) - 5} till")

        print("\nStatistik:")
        pprint(result.get('statistik', {}))

        print("\nMetrics:")
        if 'metrics' in result:
            metrics = result['metrics']
            print(f"  Coverage: {metrics['coverage_percent']}%")
            print(f"  Overtid: {metrics['overtime_hours']} timmar")
            print(f"  Regelbrott: {metrics['rule_violations']}")
            print(f"  Kostnad: {metrics['cost_kr']:,.2f} kr")
            print(f"  Kvalitetspoang: {metrics['quality_score']}/100")
        else:
            print("  (Inga metrics tillgangliga)")

        print("\nExempel pa schemarader:")
        for rad in result['schema'][:5]:
            print(f"  {rad['datum']} {rad['pass']}: {', '.join(rad['personal'][:3])}")
            if len(rad['personal']) > 3:
                print(f"    ... och {len(rad['personal']) - 3} till")

        print("[OK] Realistisk schemagenerering lyckades")
    else:
        print(f"[ERROR] Fel: {response.status_code}")
        pprint(response.json())


if __name__ == '__main__':
    try:
        print("\n" + "="*60)
        print("SCHEMA-ASSISTENT API TEST")
        print("="*60)
        print(f"\nKontrollerar att Flask-servern kors pa {BASE_URL}...")

        # Grundlaggande tester
        test_health_check()
        test_validate()
        test_generate_schedule()
        test_invalid_input()

        # Nya tester for realistisk data
        test_data_personal()
        test_data_bemanningsbehov()
        test_data_regler()
        test_generate_realistic()

        print("\n" + "="*60)
        print("[OK] ALLA TESTER LYCKADES!")
        print("="*60 + "\n")

    except requests.exceptions.ConnectionError:
        print("\n[ERROR] FEL: Kunde inte ansluta till servern.")
        print(f"Kontrollera att Flask-servern kors ({BASE_URL})")
    except AssertionError as e:
        print(f"\n[ERROR] TEST MISSLYCKADES: {e}")
    except Exception as e:
        print(f"\n[ERROR] OVANTAT FEL: {e}")
        import traceback
        traceback.print_exc()
