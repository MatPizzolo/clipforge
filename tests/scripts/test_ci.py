"""ci.yml: CI deploys leave a tag, and only that job can write (card 008, action 2).

Text checks: PyYAML isn't a project dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

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


# --- card 017: one run per commit, the docs-only path, pins and timeouts ----------------------

WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))


def test_ci_runs_once_per_commit() -> None:
    # pushes only on main (they deploy), and every pull request; never a workflow `paths:` filter
    assert (
        CI.startswith("name: CI\n")
        and "\non:\n  push:\n    branches: [main]\n  pull_request:\n" in CI
    )
    head = CI[: CI.index("\njobs:\n")]
    assert "paths" not in head


def test_check_always_runs_after_changes_and_keeps_its_name() -> None:
    check = job("check")
    assert "needs: changes\n" in check
    # the job always reports: never skipped (a skipped required check counts as passed)
    assert re.findall(r"^    if: .*$", check, re.M) == ["    if: ${{ !cancelled() }}"]
    assert "run: scripts/check.sh --python --docs" in check
    assert "run: scripts/check.sh --docs\n" in check
    assert "python3 scripts/ci_changes.py" in job("changes")
    # the docs tests need the project installed on both paths
    assert "      - run: uv sync --locked\n" in check


def test_check_fails_when_the_classifier_fails() -> None:
    check = job("check")
    first = check[check.index("    steps:\n") :].split("\n      - ", 2)[1]
    assert "if: needs.changes.result != 'success'" in first and "exit 1" in first
    # a missing output runs the whole gate; only an explicit `false` takes the docs path
    assert "outputs.code == 'true'" not in check
    assert check.count("if: needs.changes.outputs.code != 'false'") == 3
    assert check.count("if: needs.changes.outputs.code == 'false'") == 1


def test_a_push_diffs_the_trees_and_a_pr_its_own_changes() -> None:
    changes = job("changes")
    assert "DIFF=three-dot; else DIFF=two-dot" in changes
    assert '--diff "$DIFF"' in changes


def test_scope_keeps_running_on_every_pull_request() -> None:
    assert "if: github.event_name == 'pull_request'" in job("scope")


def test_deploy_and_tag_still_run_only_after_main_pushes() -> None:
    assert (
        "if: github.ref == 'refs/heads/main' && github.event_name == 'push' "
        "&& vars.DEPLOY_ENABLED == 'true'"
    ) in job("deploy")
    assert "needs: check\n" in job("deploy")


def test_a_main_push_is_classified_against_the_last_green_run() -> None:
    # the deploy job's base: a docs-only push after a failed code push still runs the full gate
    changes = job("changes")
    assert "--status success" in changes and "actions: read" in changes


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_job_has_a_timeout(workflow: Path) -> None:
    text = workflow.read_text()
    body = text[text.index("\njobs:\n") :]
    jobs = re.split(r"^  (?=[a-z][\w-]*:\n)", body, flags=re.M)[1:]
    assert jobs
    for text_of_job in jobs:
        assert re.search(r"^    timeout-minutes: \d+$", text_of_job, re.M), text_of_job[:40]


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_action_is_pinned_to_a_commit(workflow: Path) -> None:
    uses = re.findall(r"uses: (\S+)(.*)$", workflow.read_text(), re.M)
    assert uses
    for action, comment in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action), action
        assert re.fullmatch(r"  # v\d+\.\d+\.\d+", comment), f"{action}: {comment!r}"
