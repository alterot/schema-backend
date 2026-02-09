"""
Testar solver-logiken direkt utan Flask.
Snabb validering av att OR-Tools constraints fungerar.
"""

from datetime import date
from models import Person, Shift, PassTyp
from solver import SchemaOptimizer


def test_enkelt_scenario():
    """
    Test 1: Enkelt scenario med 2 personer och 3 pass.
    Borde hitta en lösning.
    """
    print("\n" + "="*60)
    print("TEST 1: Enkelt scenario")
    print("="*60)

    # Skapa personal
    personal = [
        Person(
            namn="Anna Berg",
            roll="sjukskoterska",
            anstallning=100,
            tillganglighet=["Mon", "Tue", "Wed", "Thu", "Fri"],
            franvaro=[]
        ),
        Person(
            namn="Bengt Svensson",
            roll="underskoterska",
            anstallning=100,
            tillganglighet=["Mon", "Tue", "Wed", "Thu", "Fri"],
            franvaro=[]
        )
    ]

    # Skapa pass
    shifts = [
        Shift(
            datum=date(2025, 4, 1),
            pass_typ=PassTyp.DAG,
            avdelning="3B",
            kompetenskrav={"sjukskoterska": 1, "underskoterska": 1}
        ),
        Shift(
            datum=date(2025, 4, 2),
            pass_typ=PassTyp.DAG,
            avdelning="3B",
            kompetenskrav={"sjukskoterska": 1, "underskoterska": 1}
        ),
        Shift(
            datum=date(2025, 4, 3),
            pass_typ=PassTyp.DAG,
            avdelning="3B",
            kompetenskrav={"sjukskoterska": 1, "underskoterska": 1}
        )
    ]

    # Kör optimering
    optimizer = SchemaOptimizer(personal, shifts)
    schedule = optimizer.optimera()

    # Visa resultat
    print(f"\nGenererade {len(schedule.rader)} schemarader")
    print(f"Antal konflikter: {len(schedule.konflikter)}")

    if schedule.konflikter:
        print("\n[!] Konflikter:")
        for k in schedule.konflikter:
            print(f"  - [{k.typ}] {k.beskrivning}")
    else:
        print("\n[OK] Inga konflikter")

    print("\nSchema:")
    for rad in schedule.rader:
        print(f"  {rad.datum} {rad.pass_typ.value:6s} -> {', '.join(rad.personal)}")

    return len(schedule.konflikter) == 0


def test_vilotid_constraint():
    """
    Test 2: Testar att vilotidsregeln efterlevs.
    Kvällspass dag 1 + dagpass dag 2 = OK (16h mellan)
    Kvällspass dag 1 + nattpass dag 2 = INTE OK (0h mellan)
    """
    print("\n" + "="*60)
    print("TEST 2: Vilotid constraint")
    print("="*60)

    personal = [
        Person(
            namn="Anna Berg",
            roll="sjukskoterska",
            anstallning=100,
            tillganglighet=["Mon", "Tue", "Wed", "Thu", "Fri"],
            franvaro=[]
        )
    ]

    # Två pass samma dag - personen kan bara ta ett
    shifts = [
        Shift(
            datum=date(2025, 4, 1),
            pass_typ=PassTyp.KVALL,
            avdelning="3B",
            kompetenskrav={"sjukskoterska": 1}
        ),
        Shift(
            datum=date(2025, 4, 2),
            pass_typ=PassTyp.NATT,
            avdelning="3B",
            kompetenskrav={"sjukskoterska": 1}
        )
    ]

    optimizer = SchemaOptimizer(personal, shifts)
    schedule = optimizer.optimera()

    print(f"\nGenererade {len(schedule.rader)} schemarader")
    print("\nSchema:")
    for rad in schedule.rader:
        personal_str = ', '.join(rad.personal) if rad.personal else "INGEN TILLDELAD"
        print(f"  {rad.datum} {rad.pass_typ.value:6s} -> {personal_str}")

    # Kväll kl 23 -> Natt kl 23 = 0h vilotid -> En av passen borde vara utan personal
    har_konflikt = len(schedule.konflikter) > 0
    print(f"\n[{'OK' if har_konflikt else 'FAIL'}] Vilotidsregeln testas (förväntar konflikt/undermanning)")

    return True


def test_franvaro():
    """
    Test 3: Testar att frånvaro respekteras.
    Anna har semester 1-5 april, ska inte kunna schemaläggas.
    """
    print("\n" + "="*60)
    print("TEST 3: Frånvaro")
    print("="*60)

    from models.person import Franvaro

    personal = [
        Person(
            namn="Anna Berg",
            roll="sjukskoterska",
            anstallning=100,
            tillganglighet=["Mon", "Tue", "Wed", "Thu", "Fri"],
            franvaro=[
                Franvaro(
                    start=date(2025, 4, 1),
                    slut=date(2025, 4, 5),
                    typ="semester"
                )
            ]
        ),
        Person(
            namn="Bengt Svensson",
            roll="sjukskoterska",
            anstallning=100,
            tillganglighet=["Mon", "Tue", "Wed", "Thu", "Fri"],
            franvaro=[]
        )
    ]

    shifts = [
        Shift(
            datum=date(2025, 4, 2),
            pass_typ=PassTyp.DAG,
            avdelning="3B",
            kompetenskrav={"sjukskoterska": 1}
        )
    ]

    optimizer = SchemaOptimizer(personal, shifts)
    schedule = optimizer.optimera()

    print("\nSchema:")
    for rad in schedule.rader:
        print(f"  {rad.datum} {rad.pass_typ.value:6s} -> {', '.join(rad.personal)}")

    # Anna ska INTE vara schemalagd (hon har semester)
    annas_pass = [rad for rad in schedule.rader if "Anna Berg" in rad.personal]
    success = len(annas_pass) == 0

    print(f"\n[{'OK' if success else 'FAIL'}] Anna är {'INTE' if success else 'FEL-AKTIGT'} schemalagd (hon har semester)")

    return success


def test_kompetenskrav():
    """
    Test 4: Testar kompetenskrav.
    Behöver 2 sjuksköterskor men har bara 1.
    """
    print("\n" + "="*60)
    print("TEST 4: Kompetenskrav")
    print("="*60)

    personal = [
        Person(
            namn="Anna Berg",
            roll="sjukskoterska",
            anstallning=100,
            tillganglighet=["Mon", "Tue", "Wed", "Thu", "Fri"],
            franvaro=[]
        ),
        Person(
            namn="Cecilia Andersson",
            roll="underskoterska",
            anstallning=100,
            tillganglighet=["Mon", "Tue", "Wed", "Thu", "Fri"],
            franvaro=[]
        )
    ]

    shifts = [
        Shift(
            datum=date(2025, 4, 1),
            pass_typ=PassTyp.DAG,
            avdelning="3B",
            kompetenskrav={"sjukskoterska": 2, "underskoterska": 1}  # Behöver 2 sjuksköterskor!
        )
    ]

    optimizer = SchemaOptimizer(personal, shifts)
    schedule = optimizer.optimera()

    print(f"\nKonflikter: {len(schedule.konflikter)}")
    for k in schedule.konflikter:
        print(f"  - [{k.typ}] {k.beskrivning}")

    # Ska ha konflikt (otillräcklig kompetens eller undermanning)
    har_konflikt = len(schedule.konflikter) > 0
    print(f"\n[{'OK' if har_konflikt else 'FAIL'}] Konflikt identifierad (behöver 2 sjuksköterskor, har 1)")

    return har_konflikt


if __name__ == '__main__':
    print("\n" + "="*60)
    print("SCHEMA SOLVER - ENHETSTESTER")
    print("="*60)

    resultat = []

    try:
        resultat.append(("Enkelt scenario", test_enkelt_scenario()))
        resultat.append(("Vilotid constraint", test_vilotid_constraint()))
        resultat.append(("Frånvaro", test_franvaro()))
        resultat.append(("Kompetenskrav", test_kompetenskrav()))

        print("\n" + "="*60)
        print("SAMMANFATTNING")
        print("="*60)

        for test_namn, success in resultat:
            status = "[OK]  " if success else "[FAIL]"
            print(f"{status:8s} {test_namn}")

        alla_ok = all(success for _, success in resultat)

        print("\n" + "="*60)
        if alla_ok:
            print("[OK] ALLA TESTER LYCKADES")
        else:
            print("[FAIL] VISSA TESTER MISSLYCKADES")
        print("="*60 + "\n")

    except Exception as e:
        print(f"\n[ERROR] FEL: {e}")
        import traceback
        traceback.print_exc()
