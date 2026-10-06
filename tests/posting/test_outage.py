from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.outage import OUTAGE_KEY, clear_outage, outage_since, set_outage


def test_outage_flag_is_set_once_and_cleared() -> None:
    kv = MemoryKV()
    assert outage_since(kv) is None and clear_outage(kv) is False
    assert set_outage(kv, "2026-10-01") is True
    assert set_outage(kv, "2026-10-03") is False  # sticky: the first gap's date stays
    assert outage_since(kv) == "2026-10-01" and kv.get(OUTAGE_KEY) == "2026-10-01"
    assert clear_outage(kv) is True and outage_since(kv) is None
