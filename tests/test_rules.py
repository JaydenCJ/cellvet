"""Registry invariants and documentation consistency."""

import os

from cellvet.rules import RULES, Severity


def test_rule_ids_are_unique_and_well_formed():
    assert len(RULES) == len({r.id for r in RULES.values()})
    for rule_id in RULES:
        family, number = rule_id[0], rule_id[1:]
        assert family in "ENHPW"
        assert number.isdigit() and len(number) == 3


def test_every_rule_has_a_valid_severity():
    for rule in RULES.values():
        assert rule.severity in Severity.ORDER


def test_error_rules_are_exactly_the_fresh_run_breakers():
    errors = {r.id for r in RULES.values() if r.severity == Severity.ERROR}
    assert errors == {"N201", "N202", "N203"}


def test_rule_names_are_kebab_case_and_unique():
    names = [r.name for r in RULES.values()]
    assert len(names) == len(set(names))
    for name in names:
        assert name == name.lower()
        assert " " not in name


def test_docs_rules_md_documents_every_rule():
    docs = os.path.join(os.path.dirname(__file__), "..", "docs", "rules.md")
    with open(docs, encoding="utf-8") as fh:
        text = fh.read()
    for rule in RULES.values():
        assert rule.id in text, f"{rule.id} missing from docs/rules.md"
        assert rule.name in text, f"{rule.name} missing from docs/rules.md"
