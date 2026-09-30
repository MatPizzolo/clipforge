from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.repo import PostingClaims
from tests.posting.builders import T0


def test_claims_are_per_account() -> None:
    claims = PostingClaims(MemoryKV())
    assert claims.claim_slot("a", T0) and not claims.claim_slot("a", T0)
    assert claims.claim_slot("b", T0)  # another account's same slot is its own claim
    claims.release_slot("a", T0)
    assert claims.claim_slot("a", T0)
    assert claims.claim_reminder("a", T0) and not claims.claim_reminder("a", T0)
