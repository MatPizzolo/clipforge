from clipforge.hooks.library import HookLibrary, SqlHookFreezer
from clipforge.hooks.seeds import CLIPS_SEEDS, seed
from clipforge.stages.captions import title_words
from tests.hooks.helpers import NOW


def test_seed_writes_six_approved_at_equal_weight_once(lib: HookLibrary) -> None:
    assert seed(lib, ["realtalk-clips-en"], NOW) == {"realtalk-clips-en": 6}
    assert seed(lib, ["realtalk-clips-en"], NOW) == {"realtalk-clips-en": 0}  # idempotent
    rows = lib.patterns("realtalk-clips-en")
    assert len(rows) == 6 and {w for _, _, w in rows} == {1.0}
    assert {p.status for p, _, _ in rows} == {"approved"}
    assert {v.author for _, v, _ in rows} == {"system:migration"}
    assert sum(p.control for p, _, _ in rows) == 1
    rotation = lib.rotation_for("realtalk-clips-en", "clips")
    assert len(rotation.entries) == 6 and sum(e.control for e in rotation.entries) == 1


def test_seed_dry_run_writes_nothing(lib: HookLibrary) -> None:
    assert seed(lib, ["realtalk-clips-en"], NOW, dry_run=True) == {"realtalk-clips-en": 6}
    assert lib.patterns("realtalk-clips-en") == []


def test_seed_freezes_accounts_with_running_experiments(lib: HookLibrary) -> None:
    seed(lib, ["realtalk-clips-en"], NOW, running=lambda a: [7], freezer=SqlHookFreezer(lib))
    rotation = lib.rotation_for("realtalk-clips-en", "clips")
    assert rotation.frozen_by == 7 and len(rotation.entries) == 6


def test_claim_seeds_say_no_promises() -> None:
    by_name = {d.name: d for _, d in CLIPS_SEEDS}
    for name in ("Number + stakes", "Bold claim"):
        assert "no promises" in by_name[name].structure


def test_one_control_and_six_seeds() -> None:
    assert len(CLIPS_SEEDS) == 6 and [c for c, _ in CLIPS_SEEDS].count(True) == 1
    assert all(d.fits == ["clips"] and d.max_words == 8 for _, d in CLIPS_SEEDS)


def test_seed_examples_fit_max_words_after_cleaning() -> None:
    for _, data in CLIPS_SEEDS:
        for line in data.examples.values():
            assert 0 < len(title_words(line)) <= data.max_words
