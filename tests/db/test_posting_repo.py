from clipforge.db.engine import Database
from clipforge.db.posting import SqlPostingRepo
from tests.dbhelpers import BILLY_SOURCE, make_account, seed


def test_get_reads_only_one_clip(db: Database) -> None:
    from sqlalchemy import event

    from clipforge.db.posting import SqlPostingRepo
    from clipforge.models import LEGACY_PLATFORMS
    from tests.posting.builders import item

    seed(db, make_account(), sources=[BILLY_SOURCE])
    repo = SqlPostingRepo(db)
    for n in range(1, 4):
        repo.add(item(f"clip_0{n}", start=n * 40, end=n * 40 + 30), list(LEGACY_PLATFORMS))
    statements: list[str] = []

    def capture(conn: object, cursor: object, sql: str, *rest: object) -> None:
        statements.append(sql)

    event.listen(db.engine, "before_cursor_execute", capture)
    repo.get(item("clip_02", start=80, end=110).id)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert selects and all("WHERE" in s.upper() for s in selects)
    assert "content_items.id =" in selects[0]


def _repo(db: Database) -> SqlPostingRepo:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    return SqlPostingRepo(db)


def _events(db: Database, ref: str) -> list[str]:
    from sqlalchemy import select

    from clipforge.db.tables import post_events

    with db.begin() as conn:
        rows = conn.execute(select(post_events.c.kind).where(post_events.c.item_id == ref))
        return [r.kind for r in rows]


def test_import_round_trips_and_is_idempotent(db: Database) -> None:
    from clipforge.models import Platform, PostVerdict
    from tests.posting.builders import T0, item, record, send

    repo = _repo(db)
    it = item()
    rec = record(
        it, sends=[send(1)], posted=[Platform.TIKTOK],
        verdict=PostVerdict(kind="skipped", at=T0),
    )  # fmt: skip
    assert repo.import_record(rec, chat_id=5) is True
    assert repo.get(it.id) == rec
    assert repo.import_record(rec, chat_id=5) is False
    assert repo.get(it.id) == rec
    assert _events(db, it.id) == ["imported"]


def test_import_without_assets_or_platforms(db: Database) -> None:
    from tests.posting.builders import item, record

    repo = _repo(db)
    it = item().model_copy(update={"assets": []})
    assert repo.import_record(record(it, platforms=[]), chat_id=None) is True
    got = repo.get(it.id)
    assert got is not None and got.item.assets == [] and got.platforms == []


def test_mark_unavailable_logs_once(db: Database) -> None:
    from tests.posting.builders import T0, item

    repo = _repo(db)
    it = item()
    repo.add(it, [])
    repo.mark_unavailable(it.id, T0)
    repo.mark_unavailable(it.id, T0)
    assert _events(db, it.id) == ["unavailable"]
    assert repo.get(it.id).unavailable is True  # type: ignore[union-attr]


def test_toggle_on_unqueued_platform_and_platform_subset(db: Database) -> None:
    from clipforge.models import Platform
    from tests.posting.builders import T0, item

    repo = _repo(db)
    it = item()
    repo.add(it, [Platform.TIKTOK])
    assert repo.get(it.id).platforms == [Platform.TIKTOK]  # type: ignore[union-attr]
    assert repo.toggle_posted(it.id, Platform.YOUTUBE, T0) is True
    assert repo.toggle_posted(it.id, Platform.YOUTUBE, T0) is False


def test_add_send_writes_one_event(db: Database) -> None:
    from tests.posting.builders import item, send

    repo = _repo(db)
    it = item()
    repo.add(it, [])
    repo.add_send(it.id, send(1))
    repo.add_send(it.id, send(1))
    assert _events(db, it.id) == ["sent"]


def test_event_writes_the_actor_column_and_data(db: Database) -> None:
    from sqlalchemy import select

    from clipforge.db.tables import post_events
    from clipforge.models import LEGACY_PLATFORMS, Platform
    from tests.posting.builders import T0, item

    repo = _repo(db)
    it = item()
    repo.add(it, list(LEGACY_PLATFORMS))
    repo.set_posted(it.id, Platform.TIKTOK, True, T0, actor="telegram:42")
    with db.begin() as conn:
        row = conn.execute(select(post_events.c.actor, post_events.c.data)
                           .where(post_events.c.kind == "posted")).one()  # fmt: skip
    assert row.actor == "telegram:42" and row.data["actor"] == "telegram:42"


def test_record_reads_the_publish_state(db: Database) -> None:
    from sqlalchemy import text

    from clipforge.models import LEGACY_PLATFORMS, Platform
    from tests.posting.builders import item

    repo = _repo(db)
    it = item()
    repo.add(it, list(LEGACY_PLATFORMS))
    record = repo.get(it.id)
    assert record is not None and record.publish == {}
    with db.begin() as conn:
        conn.execute(text("update posts set state = 'scheduled', publisher = 'upload_post'"
                          " where platform = 'tiktok'"))  # fmt: skip
    record = repo.get(it.id)
    assert record is not None and record.publish == {Platform.TIKTOK: "scheduled"}


def test_stamp_columns_round_trip(db: Database) -> None:  # 0003, ADR-50
    from sqlalchemy import text

    from clipforge.hooks.library import HookLibrary
    from clipforge.hooks.rotation import control_stamp
    from clipforge.hooks.seeds import seed as seed_hooks
    from clipforge.models import LEGACY_PLATFORMS
    from tests.hooks.helpers import NOW
    from tests.posting.builders import item

    repo = _repo(db)
    library = HookLibrary(db)
    seed_hooks(library, ["realtalk-clips-en"], NOW)
    stamp = control_stamp(library.rotation_for("realtalk-clips-en", "clips"), "A title")
    assert stamp is not None
    it = item().model_copy(update={"hook_stamp": stamp})
    repo.add(it, list(LEGACY_PLATFORMS))
    found = repo.get(it.id)
    assert found is not None and found.item.hook_stamp == stamp
    assert found.item.superseded_by is None
    with db.begin() as conn:
        row = conn.execute(text("select hook_pattern_id, hook_version from content_items")).one()
    assert tuple(row) == (stamp.result.pattern_id, 1)


def test_items_without_a_stamp_read_as_none(db: Database) -> None:
    from clipforge.models import LEGACY_PLATFORMS
    from tests.posting.builders import item

    repo = _repo(db)
    repo.add(item(), list(LEGACY_PLATFORMS))
    found = repo.get(item().id)
    assert found is not None and found.item.hook_stamp is None


def test_a_half_stamp_is_refused(db: Database) -> None:
    # fk_items_hook_version is MATCH SIMPLE: a pattern without a version would skip the check
    import pytest

    from clipforge.models import LEGACY_PLATFORMS, HookResult, HookStamp
    from tests.posting.builders import item

    repo = _repo(db)
    half = HookStamp(result=HookResult(pattern_id="hp_0000000a", version=None, text="t"),
                     rotation_id=None)  # fmt: skip
    with pytest.raises(ValueError, match="both"):
        repo.add(item().model_copy(update={"hook_stamp": half}), list(LEGACY_PLATFORMS))
    assert repo.get(item().id) is None
    manual = HookStamp(result=HookResult(pattern_id=None, version=None, text="t", manual=True),
                       rotation_id=None)  # fmt: skip
    assert repo.add(item().model_copy(update={"hook_stamp": manual}), list(LEGACY_PLATFORMS))
