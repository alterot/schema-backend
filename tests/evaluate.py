#!/usr/bin/env python3
"""
Evaluation Suite for Schema-assistent.
Runs test scenarios and measures scheduling quality.

Usage:
    python evaluate.py              # Run all scenarios
    python evaluate.py --scenario normal_april  # Run specific scenario
    python evaluate.py --verbose    # Show detailed output
"""

import json
import os
import sys
import argparse
from datetime import date, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from models import Person, Shift, PassTyp
from solver import SchemaOptimizer
from utils import calculate_all_metrics


# Paths
SCENARIOS_DIR = Path(__file__).parent / 'scenarios'


def load_scenario(filename: str) -> Dict[str, Any]:
    """
    Laddar ett scenario fran JSON-fil.

    Args:
        filename: Filnamn (med eller utan .json)

    Returns:
        Scenario som dict
    """
    if not filename.endswith('.json'):
        filename = f'{filename}.json'

    filepath = SCENARIOS_DIR / filename

    if not filepath.exists():
        raise FileNotFoundError(f"Scenario not found: {filepath}")

    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_shifts_for_scenario(scenario: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Genererar shifts for ett scenario baserat pa period och bemanningsbehov.

    Args:
        scenario: Scenario-dict

    Returns:
        Lista med shift-dicts
    """
    start_date = date.fromisoformat(scenario['period']['start'])
    end_date = date.fromisoformat(scenario['period']['end'])
    behov = scenario['bemanningsbehov']

    shifts = []
    current_date = start_date

    while current_date <= end_date:
        is_weekend = current_date.weekday() >= 5
        day_behov = behov['helg'] if is_weekend else behov['vardag']

        for pass_typ in ['dag', 'kvall', 'natt']:
            pass_namn = pass_typ if pass_typ != 'kvall' else 'kväll'

            shifts.append({
                'datum': current_date.isoformat(),
                'pass': pass_namn,
                'avdelning': 'Test',
                'kompetenskrav': day_behov[pass_typ]
            })

        current_date = current_date + timedelta(days=1)

    return shifts


def run_scenario(scenario: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    """
    Kor schemagenerering for ett scenario.

    Args:
        scenario: Scenario-dict
        verbose: Om True, visa detaljerad output

    Returns:
        Resultat med schema, konflikter och metrics
    """
    if verbose:
        print(f"  Converting data...")

    # Konvertera personal
    personal = [Person.from_dict(p) for p in scenario['personal']]

    # Generera shifts
    shifts_data = generate_shifts_for_scenario(scenario)
    shifts = [Shift.from_dict(s) for s in shifts_data]

    if verbose:
        print(f"  Personal: {len(personal)}")
        print(f"  Shifts: {len(shifts)}")
        print(f"  Running optimizer...")

    # Kor optimering
    optimizer = SchemaOptimizer(personal, shifts)
    schedule = optimizer.optimera()

    if verbose:
        print(f"  Calculating metrics...")

    # Berakna metrics
    metrics = calculate_all_metrics(
        schema_rader=schedule.rader,
        konflikter=schedule.konflikter,
        shifts=shifts,
        personal=personal
    )

    return {
        'scenario_name': scenario['name'],
        'schema': schedule.to_dict(),
        'metrics': metrics,
        'shifts_count': len(shifts),
        'personal_count': len(personal),
        'konflikter_count': len(schedule.konflikter)
    }


def evaluate_result(result: Dict[str, Any], expected: Dict[str, Any]) -> Dict[str, Any]:
    """
    Jamfor resultat mot forvantade outcomes.

    Args:
        result: Resultat fran run_scenario
        expected: Forvantade outcomes (min_coverage, max_overtime, min_quality)

    Returns:
        Evaluation med pass/fail for varje metric
    """
    metrics = result['metrics']

    evaluations = {}

    # Coverage check
    coverage_ok = metrics['coverage_percent'] >= expected.get('min_coverage', 0)
    evaluations['coverage'] = {
        'actual': metrics['coverage_percent'],
        'expected_min': expected.get('min_coverage', 0),
        'passed': coverage_ok
    }

    # Overtime check
    overtime_ok = metrics['overtime_hours'] <= expected.get('max_overtime', float('inf'))
    evaluations['overtime'] = {
        'actual': metrics['overtime_hours'],
        'expected_max': expected.get('max_overtime', 'N/A'),
        'passed': overtime_ok
    }

    # Quality check
    quality_ok = metrics['quality_score'] >= expected.get('min_quality', 0)
    evaluations['quality'] = {
        'actual': metrics['quality_score'],
        'expected_min': expected.get('min_quality', 0),
        'passed': quality_ok
    }

    # Overall pass
    all_passed = coverage_ok and overtime_ok and quality_ok

    return {
        'evaluations': evaluations,
        'all_passed': all_passed,
        'metrics': metrics
    }


def run_all_scenarios(verbose: bool = False) -> Dict[str, Any]:
    """
    Kor alla scenarios och samlar resultat.

    Args:
        verbose: Om True, visa detaljerad output

    Returns:
        Sammanstallning av alla resultat
    """
    results = []
    passed_count = 0
    failed_count = 0

    # Hitta alla scenario-filer
    scenario_files = list(SCENARIOS_DIR.glob('*.json'))

    if not scenario_files:
        print(f"No scenarios found in {SCENARIOS_DIR}")
        return {'results': [], 'summary': {}}

    print(f"\n{'='*60}")
    print("SCHEMA-ASSISTENT EVALUATION SUITE")
    print(f"{'='*60}")
    print(f"\nFound {len(scenario_files)} scenarios in {SCENARIOS_DIR}")
    print()

    for scenario_file in sorted(scenario_files):
        scenario_name = scenario_file.stem
        print(f"Running: {scenario_name}...", end=' ')

        try:
            # Ladda scenario
            scenario = load_scenario(scenario_name)

            if verbose:
                print()
                print(f"  Description: {scenario.get('description', 'N/A')}")

            # Kor scenario
            result = run_scenario(scenario, verbose=verbose)

            # Evaluera resultat
            expected = scenario.get('expected_outcome', {})
            evaluation = evaluate_result(result, expected)

            # Samla resultat
            scenario_result = {
                'name': scenario_name,
                'description': scenario.get('description', ''),
                'result': result,
                'evaluation': evaluation
            }
            results.append(scenario_result)

            # Uppdatera pass/fail
            if evaluation['all_passed']:
                passed_count += 1
                status = "PASS"
            else:
                failed_count += 1
                status = "FAIL"

            if not verbose:
                print(f"[{status}]")
            else:
                print(f"  Status: [{status}]")

            # Visa metrics
            m = result['metrics']
            print(f"    Coverage: {m['coverage_percent']}% | "
                  f"Overtime: {m['overtime_hours']}h | "
                  f"Quality: {m['quality_score']}/100 | "
                  f"Violations: {m['rule_violations']}")

            if not evaluation['all_passed']:
                # Visa vilka som failade
                for metric_name, eval_data in evaluation['evaluations'].items():
                    if not eval_data['passed']:
                        if 'expected_min' in eval_data:
                            print(f"    ^ {metric_name}: {eval_data['actual']} < {eval_data['expected_min']} (min)")
                        else:
                            print(f"    ^ {metric_name}: {eval_data['actual']} > {eval_data['expected_max']} (max)")

        except Exception as e:
            print(f"[ERROR] {e}")
            failed_count += 1
            results.append({
                'name': scenario_name,
                'error': str(e)
            })

        print()

    # Sammanstallning
    summary = {
        'total_scenarios': len(scenario_files),
        'passed': passed_count,
        'failed': failed_count,
        'pass_rate': round((passed_count / len(scenario_files)) * 100, 1) if scenario_files else 0,
        'avg_coverage': calculate_average(results, 'coverage_percent'),
        'avg_quality': calculate_average(results, 'quality_score'),
        'avg_overtime': calculate_average(results, 'overtime_hours')
    }

    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Scenarios: {summary['total_scenarios']}")
    print(f"Passed: {summary['passed']} | Failed: {summary['failed']}")
    print(f"Pass Rate: {summary['pass_rate']}%")
    print()
    print(f"Average Coverage: {summary['avg_coverage']}%")
    print(f"Average Quality Score: {summary['avg_quality']}/100")
    print(f"Average Overtime: {summary['avg_overtime']}h")
    print(f"{'='*60}\n")

    return {
        'results': results,
        'summary': summary
    }


def calculate_average(results: List[Dict], metric_name: str) -> float:
    """Beraknar genomsnitt for en metric over alla resultat."""
    values = []
    for r in results:
        if 'result' in r and 'metrics' in r['result']:
            values.append(r['result']['metrics'].get(metric_name, 0))
    return round(sum(values) / len(values), 1) if values else 0


def generate_report(evaluation_results: Dict[str, Any]) -> str:
    """
    Genererar en markdown-rapport fran evaluation results.

    Args:
        evaluation_results: Resultat fran run_all_scenarios

    Returns:
        Markdown-formaterad rapport
    """
    summary = evaluation_results['summary']
    results = evaluation_results['results']

    lines = [
        "# Schema-assistent Evaluation Report",
        "",
        f"**Date:** {date.today().isoformat()}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Scenarios | {summary['total_scenarios']} |",
        f"| Passed | {summary['passed']} |",
        f"| Failed | {summary['failed']} |",
        f"| Pass Rate | {summary['pass_rate']}% |",
        f"| Avg Coverage | {summary['avg_coverage']}% |",
        f"| Avg Quality | {summary['avg_quality']}/100 |",
        f"| Avg Overtime | {summary['avg_overtime']}h |",
        "",
        "## Scenario Results",
        ""
    ]

    for r in results:
        name = r.get('name', 'Unknown')
        status = "PASS" if r.get('evaluation', {}).get('all_passed', False) else "FAIL"

        lines.append(f"### {name}")
        lines.append("")

        if 'error' in r:
            lines.append(f"**Status:** ERROR - {r['error']}")
        else:
            desc = r.get('description', '')
            if desc:
                lines.append(f"*{desc}*")
                lines.append("")

            lines.append(f"**Status:** {status}")
            lines.append("")

            m = r['result']['metrics']
            lines.append(f"| Metric | Actual | Expected | Status |")
            lines.append(f"|--------|--------|----------|--------|")

            ev = r['evaluation']['evaluations']
            for metric, data in ev.items():
                actual = data['actual']
                if 'expected_min' in data:
                    expected = f">= {data['expected_min']}"
                else:
                    expected = f"<= {data['expected_max']}"
                status_emoji = "OK" if data['passed'] else "X"
                lines.append(f"| {metric.capitalize()} | {actual} | {expected} | {status_emoji} |")

        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description='Run evaluation suite for Schema-assistent')
    parser.add_argument('--scenario', '-s', help='Run specific scenario (without .json)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed output')
    parser.add_argument('--report', '-r', help='Save markdown report to file')

    args = parser.parse_args()

    if args.scenario:
        # Kor specifikt scenario
        print(f"\nRunning scenario: {args.scenario}")
        scenario = load_scenario(args.scenario)
        result = run_scenario(scenario, verbose=args.verbose)
        evaluation = evaluate_result(result, scenario.get('expected_outcome', {}))

        print(f"\nMetrics:")
        for k, v in result['metrics'].items():
            print(f"  {k}: {v}")

        print(f"\nEvaluation:")
        for k, v in evaluation['evaluations'].items():
            status = "PASS" if v['passed'] else "FAIL"
            print(f"  {k}: [{status}] {v['actual']}")

        print(f"\nOverall: {'PASS' if evaluation['all_passed'] else 'FAIL'}")

    else:
        # Kor alla scenarios
        results = run_all_scenarios(verbose=args.verbose)

        if args.report:
            report = generate_report(results)
            with open(args.report, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Report saved to: {args.report}")


if __name__ == '__main__':
    main()
