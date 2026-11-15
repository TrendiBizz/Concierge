"""Env files are data, not shell.

Measured live 2026-11-15: check-inbound-chain.sh sourced /opt/trendi/shared/api.env, whose
ASTERISK_CHANNEL_DIAL value is `PJSIP/<number>@concierge`. Sourcing it is a redirect — bash
printed "number: No such file or directory" on every cron run and left the variable as the
truncated "PJSIP/". The API container never saw the fault (compose parses the file as data), so
only our own tooling was wrong.
"""
import pathlib
import shutil
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]
VPS = REPO / "scripts" / "vps"


def test_the_loader_keeps_an_env_value_that_a_shell_would_eat(tmp_path):
    env = tmp_path / "api.env"
    env.write_text(
        "# a comment\n"
        "ADMIN_TOKEN=abc123\n"
        "ASTERISK_CHANNEL_DIAL=PJSIP/<number>@concierge\n"
        "QUOTED=\"two words\"\n"
        "NOT A LINE\n"
    )
    script = (
        f'. "{VPS / "env_lib.sh"}"; load_env "{env}" || exit 9\n'
        'printf "%s\\n" "$ADMIN_TOKEN" "$ASTERISK_CHANNEL_DIAL" "$QUOTED"\n'
    )
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == ["abc123", "PJSIP/<number>@concierge", "two words"]
    assert done.stderr == "", f"the loader must not run the value: {done.stderr}"


def test_the_loader_survives_a_missing_file_without_killing_the_caller():
    script = f'. "{VPS / "env_lib.sh"}"; if load_env /nonexistent/api.env; then exit 1; fi; echo alive'
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert done.returncode == 0 and "alive" in done.stdout
    assert done.stderr == ""


def test_no_operational_script_sources_the_shared_env_file():
    """Sourcing it works only by accident, and it silently truncates any value with < > & or a #."""
    offenders = []
    for path in sorted((REPO / "scripts").rglob("*.sh")):
        text = path.read_text(errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "api.env" not in stripped and "phone.env" not in stripped:
                continue
            if stripped.startswith(".") or stripped.startswith("source ") or "set -a; ." in stripped:
                if "load_env" not in stripped:
                    offenders.append(f"{path.relative_to(REPO)}: {stripped[:90]}")
    assert not offenders, "source the env file through scripts/vps/env_lib.sh instead:\n" + "\n".join(offenders)


def test_the_inbound_chain_check_uses_the_loader_and_runs_clean():
    body = (VPS / "check-inbound-chain.sh").read_text()
    assert "env_lib.sh" in body and "load_env" in body
    assert "set -a; . \"$ENV_FILE\"" not in body

    # Run it against a fixture env file with the real shape of the live value. The API is not
    # reachable from the test, so the script is expected to fail at the request — what matters is
    # that it gets that far without a shell error.
    if shutil.which("curl") is None:
        return
    done = subprocess.run(
        ["bash", str(VPS / "check-inbound-chain.sh")],
        capture_output=True, text=True, timeout=30,
        env={"PATH": "/usr/bin:/bin", "ENV_FILE": str(VPS / "tests" / "fixture-api.env"),
             "API": "http://127.0.0.1:9"},
    )
    assert "No such file or directory" not in done.stderr, done.stderr
    assert "readiness request failed" in done.stderr or done.returncode in (0, 1, 2), done.stderr
