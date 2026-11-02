from collections import Counter

from clipforge.hooks.rotation import (
    clip_seed,
    control_entry,
    control_stamp,
    pick,
    resolve,
    seed_for,
    weights_of,
)
from tests.hooks.builders import entry, pattern_pair, rotation


def test_pick_is_deterministic() -> None:
    r = rotation(entry("hp_a", 1.0), entry("hp_b", 1.0))
    seed = clip_seed("abc", 1.0, 31.5, r)
    assert pick(r, seed) == pick(r, seed)
    assert pick(r, seed) == pick(rotation(entry("hp_b", 1.0), entry("hp_a", 1.0)), seed)


def test_pick_follows_weights() -> None:
    r = rotation(entry("hp_a", 1.0), entry("hp_b", 3.0))
    picks = (pick(r, seed_for(str(i))) for i in range(6000))
    counts = Counter(p.pattern_id for p in picks if p is not None)
    expected = {"hp_a": 1500, "hp_b": 4500}
    chi2 = sum((counts[k] - v) ** 2 / v for k, v in expected.items())
    assert chi2 < 10.83  # p = 0.001, 1 degree of freedom


def test_clip_seed_depends_on_the_moment_and_the_rotation() -> None:
    r = rotation(entry("hp_a", 1.0))
    seeds = {
        clip_seed("abc", 1.0, 31.5, r),
        clip_seed("abd", 1.0, 31.5, r),
        clip_seed("abc", 1.0, 31.6, r),
        clip_seed("abc", 1.0, 31.5, rotation(entry("hp_a", 2.0))),
    }
    assert len(seeds) == 4


def test_empty_rotation_picks_none() -> None:  # Review Focus 5
    assert pick(rotation(), seed_for("x")) is None
    assert pick(None, seed_for("x")) is None


def test_resolve_keeps_approved_fitting_weighted_current_versions() -> None:
    pairs = [
        pattern_pair("hp_a", status="approved", fits=["clips"]),
        pattern_pair("hp_b", status="draft", fits=["clips"]),
        pattern_pair("hp_c", status="approved", fits=["story"]),
        pattern_pair("hp_d", status="approved", fits=["clips"]),
        pattern_pair("hp_e", status="approved", fits=["clips"]),  # no weight row
        pattern_pair("hp_f", status="approved", fits=["clips"], version=1, current=2),
    ]
    weights = {"hp_a": 1.0, "hp_b": 1.0, "hp_c": 1.0, "hp_d": 0.0, "hp_f": 1.0}
    r = resolve("realtalk-clips-en", "clips", pairs, weights, None)
    assert [e.pattern_id for e in r.entries] == ["hp_a"] and r.frozen_by is None


def test_open_freeze_wins() -> None:
    frozen = rotation(entry("hp_old", 1.0)).model_copy(update={"frozen_by": 1})
    pairs = [pattern_pair("hp_a", status="approved", fits=["clips"])]
    assert resolve("realtalk-clips-en", "clips", pairs, {"hp_a": 1.0}, frozen) == frozen


def test_control_entry() -> None:
    r = rotation(entry("hp_a", 1.0), entry("hp_ctl", 1.0, control=True))
    control = control_entry(r)
    assert control is not None and control.pattern_id == "hp_ctl"
    assert control_entry(None) is None and control_entry(rotation(entry("hp_a", 1.0))) is None


def test_control_stamp() -> None:
    r = rotation(entry("hp_ctl", 1.0, control=True), entry("hp_a", 2.0))
    stamp = control_stamp(r, "Highlight title")
    assert stamp is not None
    assert (stamp.result.pattern_id, stamp.result.version, stamp.result.text) == (
        "hp_ctl",
        1,
        "Highlight title",
    )
    assert stamp.result.drawn is False and stamp.rotation_id == r.id
    assert stamp.weights == weights_of(r) == {"hp_ctl@1": 1.0, "hp_a@1": 2.0}
    assert control_stamp(None, "t") is None
    assert control_stamp(rotation(entry("hp_a", 1.0)), "t") is None
