"""ci.yml: CI deploys leave a tag, and only that job can write (card 008, action 2).

Text checks: PyYAML isn't a project dependency.
"""

from __future__ import annotations

import re

from tests.scripts._load import ROOT

CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text()


def job(name: str) -> str:
    """The text of one job: from `  <name>:` to the next top-level job or the end."""
    match = re.search(rf"^  {name}:\n(.*?)(?=^  [a-z][\w-]*:\n|\Z)", CI, re.M | re.S)
    assert match, name
    return match.group(1)


def test_the_workflow_is_read_only_by_default() -> None:
    assert "\npermissions:\n  contents: read\n" in CI


def test_only_the_tag_job_can_write_and_only_contents() -> None:
    assert re.findall(r"^ +[\w-]+: write$", CI, re.M) == ["      contents: write"]
    assert "    permissions:\n      contents: write\n    steps:" in job("tag")
    assert "contents: read" in job("deploy")


def test_the_tag_job_follows_a_successful_deploy() -> None:
    tag = job("tag")
    assert "needs: deploy\n" in tag
    assert "if: needs.deploy.outputs.tag != ''" in tag
    deploy = job("deploy")
    # the tag is handed over only by a step after `modal deploy`
    assert deploy.index("modal deploy src/clipforge/app.py") < deploy.index("id: deployed")


def test_the_tag_and_log_line_match_deploy_sh() -> None:
    assert "tag=deploy-$(date -u -d \"@$NOW\" '+%Y%m%d-%H%M')" in job("deploy")
    tag = job("tag")
    assert 'git push origin "$TAG"' in tag
    assert "$GITHUB_STEP_SUMMARY" in tag
    # the commit message reaches the shell only through env, never inlined in `run:`
    run = tag[tag.index("run: |") :]
    assert "${{" not in run
