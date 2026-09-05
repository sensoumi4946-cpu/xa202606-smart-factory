from pathlib import Path

from scripts.validate_sample_data import validate_file

ROOT = Path(__file__).resolve().parents[2]


def test_every_sample_is_contract_semantic_and_binding_valid():
    results = validate_file(
        ROOT / "data" / "samples" / "five_subsystems.jsonl",
        ROOT / "bindings.ttl",
    )
    assert len(results) == 5
    assert all(result.contract_valid for result in results)
    assert all(result.semantic_valid for result in results)
    assert all(result.binding_covered for result in results)
