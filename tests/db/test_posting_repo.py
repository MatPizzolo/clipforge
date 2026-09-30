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
