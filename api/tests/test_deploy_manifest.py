"""Production must be traceable to a commit, and hand edits on the box must be visible.

On 2026-11-15 the website was published from a directory that was not a git repository. Three agents
edited it, 17 files including three pages reached production without ever being committed, and
nothing noticed — a green health check does not imply that the box matches the repo.
"""
import importlib.util
import pathlib
import re

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "vps" / "healthcheck.py"
_spec = importlib.util.spec_from_file_location("concierge_healthcheck_deploy", SCRIPT)
healthcheck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(healthcheck)

MANIFEST = {"commit": "abc1234", "files": {"index.html": "aaa", "sitemap.xml": "bbb"}}
STAMPED = {"index.html": "aaa", "sitemap.xml": "bbb"}


def test_a_tree_matching_the_manifest_is_clean():
    assert healthcheck.manifest_problems(MANIFEST, STAMPED) == []


def test_a_file_edited_on_the_box_is_reported():
    actual = dict(STAMPED, **{"index.html": "zzz"})
    problems = healthcheck.manifest_problems(MANIFEST, actual)
    assert any("1 file(s) changed on the box: index.html" in p for p in problems)


def test_a_file_deleted_on_the_box_is_reported():
    actual = {"index.html": "aaa"}
    problems = healthcheck.manifest_problems(MANIFEST, actual)
    assert any("1 file(s) missing: sitemap.xml" in p for p in problems)


def test_a_file_added_outside_the_repo_is_reported():
    actual = dict(STAMPED, **{"hotfix.html": "ccc"})
    problems = healthcheck.manifest_problems(MANIFEST, actual)
    assert any("1 file(s) added outside the repo: hotfix.html" in p for p in problems)


def test_an_empty_manifest_is_a_problem_rather_than_a_pass():
    assert healthcheck.manifest_problems({"files": {}}, STAMPED) == ["manifest lists no files"]


def test_the_check_is_wired_into_the_report():
    loops = re.findall(r"for step in \(([^)]*)\)", SCRIPT.read_text(), re.S)
    assert any("check_deploy_manifest" in loop for loop in loops), "check_deploy_manifest must run"


def test_the_deploy_script_refuses_a_dirty_tree():
    """The enforcement that matters: an uncommitted change cannot be published."""
    script = (SCRIPT.parent / "deploy-site.sh").read_text()
    assert "REFUSING" in script
    assert "git -C \"$REPO_ROOT\" diff --quiet" in script
    assert "ls-files --others --exclude-standard" in script, "untracked files must block a deploy"


def test_the_site_source_is_the_repo_not_a_loose_directory():
    script = (SCRIPT.parent / "deploy-site.sh").read_text()
    assert 'SRC="${SITE_SRC:-$REPO_ROOT/website}"' in script, \
        "the deploy source must default to the tracked website directory"
