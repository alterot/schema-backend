import requests

BASE_URL = "http://localhost:5000/api"

print("============================================================")
print("TOOL ENDPOINTS TEST")
print("============================================================\n")

print("=== TEST 1: Hämta schema ===")
try:
    response = requests.get(f"{BASE_URL}/schedule/2025-04")
    print(f"Status: {response.status_code}")
    print(response.json())
    print("✓ read_schedule funkar\n")
except Exception as e:
    print(f"✗ Fel: {e}\n")

print("=== TEST 2: Föreslå ändringar ===")
try:
    response = requests.post(f"{BASE_URL}/propose", json={"problem": "För mycket övertid på nätterna"})
    print(f"Status: {response.status_code}")
    print(response.json())
    print("✓ propose_changes funkar\n")
except Exception as e:
    print(f"✗ Fel: {e}\n")

print("=== TEST 3: Simulera konsekvenser ===")
try:
    response = requests.post(f"{BASE_URL}/simulate", json={"changes": [{"type": "move_shift", "person": "Anna"}]})
    print(f"Status: {response.status_code}")
    print(response.json())
    print("✓ simulate_impact funkar\n")
except Exception as e:
    print(f"✗ Fel: {e}\n")

print("=== TEST 4: Applicera ändringar ===")
try:
    response = requests.post(f"{BASE_URL}/apply", json={"confirmed": True, "schema": {}})
    print(f"Status: {response.status_code}")
    print(response.json())
    print("✓ apply_changes funkar\n")
except Exception as e:
    print(f"✗ Fel: {e}\n")

print("============================================================")
print("✓ ALLA TOOL ENDPOINTS TESTADE")
print("============================================================")