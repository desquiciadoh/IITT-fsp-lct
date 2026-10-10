"""ML-12: Test Twins are parallel forms of one screening blueprint. Pure: no Django."""
from __future__ import annotations

import json

import pytest
from assessment.engine.blueprint import blueprint_for
from assessment.engine.content import load_content
from assessment.engine.twins import allocate_slots, create_test_twins, generate_twins_for_position
from assessment.families.base import GRADES
from assessment.families.registry import all_families, make_rng

SECRET = b"test-secret-not-for-production"
CASES = [("backend", ("python", "postgresql", "docker"), "middle"), ("frontend", ("react", "typescript", "css"), "senior"),
         ("ml_data", ("pytorch", "pandas"), "junior"), ("backend", (), "senior"), ("ml_data", (), "intern")]


def test_slot_allocation_largest_remainder_by_hand():
    # 0.5·5 = 2.5, 0.3·5 = 1.5, 0.2·5 = 1.0 -> floors 2, 1, 1 = 4; one extra to the larger remainder,
    # tied 0.5 vs 0.5 -> topic id order: "a" before "b"
    assert allocate_slots([("b", 0.5), ("a", 0.3), ("c", 0.2)], 5) == ["b", "b", "a", "a", "c"]
    assert allocate_slots([("x", 1.0)], 3) == ["x", "x", "x"]
    assert allocate_slots([("x", 1.0)], 0) == []


@pytest.mark.parametrize("spec, skills, grade", CASES)
def test_twins_are_parallel_forms(spec, skills, grade):
    t = create_test_twins(spec, skills, SECRET, target_grade=grade, n_items=8, seed="p-1")
    a, b = t.twin_a.items, t.twin_b.items
    assert len(a) == len(b) == 8
    # same family per slot -> identical parameters and information, different instances
    assert [i.family_id for i in a] == [i.family_id for i in b]
    assert t.comparison.difficulty_diff == 0 and t.comparison.discrimination_diff == 0
    assert t.comparison.duration_diff == 0 and t.comparison.tif_max_abs_diff == 0
    assert t.comparison.identical_fingerprints == 0 and t.comparison.topic_match
    assert all(x.view != y.view for x, y in zip(a, b, strict=True))
    # slots follow the blueprint, and every item's family really belongs to the slot's topic
    bp = blueprint_for(spec, list(skills))
    assert [i.topic for i in a] == allocate_slots(bp, 8)
    metas = {fid: fam.meta for fid, fam in all_families().items()}
    assert all(metas[i.family_id].topic == i.topic and spec in metas[i.family_id].specs for i in a)
    assert all(i.level in GRADES for i in a)


def test_a_topic_with_several_slots_rotates_its_families():
    t = create_test_twins("backend", (), SECRET, n_items=16, seed=1)
    by_topic: dict[str, list[str]] = {}
    for i in t.twin_a.items:
        by_topic.setdefault(i.topic, []).append(i.family_id)
    families = {fid for fid, fam in all_families().items() if "backend" in fam.meta.specs}
    for topic, fids in by_topic.items():
        available = sum(1 for fid in families if all_families()[fid].meta.topic == topic)
        assert len(set(fids)) == min(len(fids), available), (topic, fids)


def test_twins_are_deterministic_per_secret_and_seed():
    one = create_test_twins("frontend", ("react",), SECRET, n_items=6, seed=7).to_dict()
    assert one == create_test_twins("frontend", ("react",), SECRET, n_items=6, seed=7).to_dict()
    assert one != create_test_twins("frontend", ("react",), SECRET, n_items=6, seed=8).to_dict()
    assert one != create_test_twins("frontend", ("react",), b"another-secret", n_items=6, seed=7).to_dict()


def test_no_key_or_fingerprint_anywhere_in_the_output():
    t = create_test_twins("ml_data", ("numpy",), SECRET, n_items=8, seed=3)
    blob = json.dumps(t.to_dict(), ensure_ascii=False)
    assert '"key"' not in blob and "fingerprint" not in blob.replace("identical_fingerprints", "")
    registry = all_families()
    for twin, label in ((t.twin_a, "A"), (t.twin_b, "B")):
        for item in twin.items:
            assert item.fingerprint not in blob
            # regenerate the instance server-side: its key is not in the output either
            inst = registry[item.family_id].generate(make_rng(SECRET, f"twins|3|ml_data|{label}", item.family_id,
                                                              item.seq))
            if label == "A":
                assert inst.fingerprint == item.fingerprint
            if inst.input == "number":
                assert f'"{inst.key}"' not in blob


def test_bad_arguments_are_refused():
    with pytest.raises(ValueError):
        create_test_twins("devops", (), SECRET)
    with pytest.raises(ValueError):
        create_test_twins("backend", (), SECRET, target_grade="lead")
    with pytest.raises(ValueError):
        create_test_twins("backend", (), SECRET, n_items=0)
    with pytest.raises(ValueError):
        create_test_twins("backend", (), b"")                 # make_rng refuses an empty secret


def test_position_dict_with_tuples():
    pos = {"position_id": "P-042", "specialization": "backend", "grades": ("senior",),
           "must_skills": ("python", "postgresql"), "nice_skills": ("kubernetes",)}
    t = generate_twins_for_position(pos, SECRET)
    assert t.spec == "backend" and t.target_grade == "senior" and len(t.twin_a.items) == 8
    d = t.to_dict()
    assert set(d) == {"specialization", "target_grade", "blueprint", "twin_a", "twin_b", "comparison"}
    assert sum(row["items_allocated"] for row in d["blueprint"]) == 8
    assert {row["topic"] for row in d["blueprint"]} <= set(load_content().topics_for("backend"))
