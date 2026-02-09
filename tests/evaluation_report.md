# Schema-assistent Evaluation Report

**Date:** 2026-02-09

## Summary

| Metric | Value |
|--------|-------|
| Total Scenarios | 5 |
| Passed | 5 |
| Failed | 0 |
| Pass Rate | 100.0% |
| Avg Coverage | 100.0% |
| Avg Quality | 96.4/100 |
| Avg Overtime | 0.0h |

## Scenario Results

### high_sickness

*Hog sjukfranvaro - 2 personer sjuka samtidigt. Testar schemalagning under press.*

**Status:** PASS

| Metric | Actual | Expected | Status |
|--------|--------|----------|--------|
| Coverage | 100.0 | >= 90 | OK |
| Overtime | 0.0 | <= 15 | OK |
| Quality | 94 | >= 75 | OK |

### normal_april

*Baseline scenario - Normal april med tillracklig personal. Testar grundlaggande schemalagning.*

**Status:** PASS

| Metric | Actual | Expected | Status |
|--------|--------|----------|--------|
| Coverage | 100.0 | >= 95 | OK |
| Overtime | 0.0 | <= 10 | OK |
| Quality | 97 | >= 85 | OK |

### simple_test

*Enkelt testscenario - 7 dagar med minimal bemanning for att verifiera att evaluation fungerar.*

**Status:** PASS

| Metric | Actual | Expected | Status |
|--------|--------|----------|--------|
| Coverage | 100.0 | >= 95 | OK |
| Overtime | 0.0 | <= 10 | OK |
| Quality | 100 | >= 85 | OK |

### understaffed

*Underbemannat scenario - Farre personal an idealt. Testar schemalagning med begransade resurser.*

**Status:** PASS

| Metric | Actual | Expected | Status |
|--------|--------|----------|--------|
| Coverage | 100.0 | >= 90 | OK |
| Overtime | 0.0 | <= 15 | OK |
| Quality | 97 | >= 75 | OK |

### vacation_peak

*Semestertopp - 3 personer pa semester samtidigt. Testar schemalagning under semesterperiod.*

**Status:** PASS

| Metric | Actual | Expected | Status |
|--------|--------|----------|--------|
| Coverage | 100.0 | >= 85 | OK |
| Overtime | 0.0 | <= 20 | OK |
| Quality | 94 | >= 70 | OK |
