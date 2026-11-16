"""The customer-mode Hermes must plan, never act: only these three tools may be enabled for the API channel."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FILE = ROOT / "scripts" / "vps" / "hermes.customer.toolsets.yaml"
SAFE = {"memory", "session_search", "todo"}
DANGEROUS = {"terminal", "file", "browser", "code_execution", "delegation", "cronjob", "web",
             "computer_use", "connections", "image_gen", "x_search"}


def test_the_customer_toolset_allows_only_planning_tools():
    enabled = set(yaml.safe_load(FILE.read_text())["platform_toolsets"]["api_server"])
    assert enabled <= SAFE
    assert not enabled & DANGEROUS


def test_hermes_sh_refuses_to_install_a_toolset_that_leaves_a_dangerous_tool_on():
    script = (ROOT / "scripts" / "vps" / "hermes.sh").read_text()
    for tool in DANGEROUS:
        assert tool in script.split("toolsets-install)")[1].split("gateway-start)")[0]
