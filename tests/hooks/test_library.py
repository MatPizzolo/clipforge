import pytest

from clipforge.db.engine import Database
from clipforge.hooks.library import HookError, HookLibrary, HookNotFound
from tests.dbhelpers import insert_account
from tests.hooks.helpers import (
    DATA,
    NOW,
    approved,
    last_event,
    version_count,
)


def test_draft_then_approve_enters_rotation_at_weight_one(lib: HookLibrary) -> None:
    p = lib.create_draft("realtalk-clips-en", DATA, "web:mat", NOW)
    assert p.status == "draft" and p.id.startswith("hp_") and len(p.id) == 11
    assert lib.rotation_for("realtalk-clips-en", "clips").entries == []
    lib.approve(p.id, "realtalk-clips-en", "web:mat", NOW)
    [e] = lib.rotation_for("realtalk-clips-en", "clips").entries
    assert (e.pattern_id, e.version, e.weight, e.data) == (p.id, 1, 1.0, DATA)


def test_edit_writes_next_version_and_keeps_the_old(lib: HookLibrary, db: Database) -> None:
    p = approved(lib)
    v2 = lib.edit(p.id, DATA.model_copy(update={"structure": "Sharper"}), "tighter", "web:mat", NOW)
    assert v2.n == 2 and v2.note == "tighter" and version_count(db, p.id) == 2
    [e] = lib.rotation_for("realtalk-clips-en", "clips").entries
    assert e.version == 2 and e.data.structure == "Sharper"
    assert last_event(db, "version").data == {"from": 1, "to": 2, "note": "tighter"}


def test_weight_change_logs_from_to_reason(lib: HookLibrary, db: Database) -> None:
    p = approved(lib)
    lib.set_weight("realtalk-clips-en", p.id, 0.5, "weak on rejects", "web:mat", NOW)
    ev = last_event(db, "weight")
    assert ev.data == {"from": 1.0, "to": 0.5, "reason": "weak on rejects"}
    assert ev.actor == "web:mat" and ev.account_id == "realtalk-clips-en"
    assert lib.rotation_for("realtalk-clips-en", "clips").entries[0].weight == 0.5


def test_weight_needs_a_reason_and_a_valid_actor(lib: HookLibrary) -> None:
    p = approved(lib)
    with pytest.raises(HookError, match="reason"):
        lib.set_weight("realtalk-clips-en", p.id, 0.5, "  ", "web:mat", NOW)
    with pytest.raises(HookError, match="actor"):
        lib.set_weight("realtalk-clips-en", p.id, 0.5, "x", "nobody", NOW)
    with pytest.raises(HookError, match="weight"):
        lib.set_weight("realtalk-clips-en", p.id, -1, "x", "web:mat", NOW)


def test_retire_sets_weight_zero_and_leaves_rotation(lib: HookLibrary, db: Database) -> None:
    p = approved(lib)
    assert lib.retire(p.id, "realtalk-clips-en", "web:mat", NOW).status == "retired"
    assert lib.rotation_for("realtalk-clips-en", "clips").entries == []
    assert last_event(db, "weight").data == {"from": 1.0, "to": 0.0, "reason": "retired"}
    lib.approve(p.id, "realtalk-clips-en", "web:mat", NOW, weight=2.0)  # can come back
    assert lib.rotation_for("realtalk-clips-en", "clips").entries[0].weight == 2.0


def test_share_moves_scope_and_pair_sees_it_at_weight_zero(lib: HookLibrary, db: Database) -> None:
    insert_account(db, "realtalk-clips-es", blueprint="realtalk-clips")
    insert_account(db, "founder-tapes-en", blueprint="founder-tapes")
    p = approved(lib)
    shared = lib.share(p.id, "web:mat", NOW)
    assert (shared.account_id, shared.blueprint_name) == (None, "realtalk-clips")
    weights = {x.id: w for x, _, w in lib.patterns("realtalk-clips-es")}
    assert weights == {p.id: 0.0}
    assert lib.rotation_for("realtalk-clips-es", "clips").entries == []
    assert [e.pattern_id for e in lib.rotation_for("realtalk-clips-en", "clips").entries] == [p.id]
    assert lib.patterns("founder-tapes-en") == []
    with pytest.raises(HookNotFound):
        lib.approve(p.id, "founder-tapes-en", "web:mat", NOW)
    with pytest.raises(HookError, match="already shared"):
        lib.share(p.id, "web:mat", NOW)


def test_unknown_pattern_or_account_is_not_found(lib: HookLibrary) -> None:
    with pytest.raises(HookNotFound, match="no pattern"):
        lib.approve("hp_zzzzzzzz", "realtalk-clips-en", "web:mat", NOW)
    with pytest.raises(HookNotFound, match="no account"):
        lib.create_draft("nobody-en", DATA, "web:mat", NOW)
    with pytest.raises(HookNotFound, match="no account"):
        lib.rotation_for("nobody-en", "clips")


def test_another_accounts_pattern_is_not_found(lib: HookLibrary, db: Database) -> None:
    insert_account(db, "founder-tapes-en", blueprint="founder-tapes")
    p = approved(lib)
    with pytest.raises(HookNotFound):
        lib.set_weight("founder-tapes-en", p.id, 2.0, "x", "web:mat", NOW)


def test_rotation_fits_the_producer(lib: HookLibrary) -> None:
    p = lib.create_draft("realtalk-clips-en", DATA.model_copy(update={"fits": ["story"]}),
                         "web:mat", NOW)  # fmt: skip
    lib.approve(p.id, "realtalk-clips-en", "web:mat", NOW)
    assert lib.rotation_for("realtalk-clips-en", "clips").entries == []
    assert len(lib.rotation_for("realtalk-clips-en", "story").entries) == 1


def test_retiring_a_shared_pattern_leaves_the_other_accounts(
    lib: HookLibrary, db: Database
) -> None:
    insert_account(db, "realtalk-clips-es", blueprint="realtalk-clips")
    p = approved(lib)
    lib.share(p.id, "web:mat", NOW)
    lib.approve(p.id, "realtalk-clips-es", "web:mat", NOW)
    retired = lib.retire(p.id, "realtalk-clips-en", "web:mat", NOW)
    assert retired.status == "approved"  # still the sibling's
    assert lib.rotation_for("realtalk-clips-en", "clips").entries == []
    assert len(lib.rotation_for("realtalk-clips-es", "clips").entries) == 1


def test_the_control_is_never_shared(lib: HookLibrary) -> None:
    p = lib.create_draft("realtalk-clips-en", DATA, "web:mat", NOW, control=True)
    with pytest.raises(HookError, match="control"):
        lib.share(p.id, "web:mat", NOW)
