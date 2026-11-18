"""npm audit gate: fail on high/critical except explicitly accepted GHSAs."""

from __future__ import annotations

from pathlib import Path

from scripts import npm_audit_gate as gate


def _vuln(severity, via):
    return {"severity": severity, "via": via}


def _advisory(ghsa):
    return {"url": f"https://github.com/advisories/{ghsa}", "title": ghsa}


def _report():
    return {
        "vulnerabilities": {
            "picomatch": _vuln("high", [_advisory("GHSA-fc5q-39xc-vjpf")]),
            "@jest/core": _vuln("high", ["picomatch"]),
            "jest": _vuln("high", ["@jest/core"]),
        }
    }


def test_transitive_chain_inherits_the_allowlisted_advisory():
    accepted, blocking = gate.evaluate(_report(), {"GHSA-fc5q-39xc-vjpf"})
    assert blocking == []
    assert {name for name, _ids in accepted} == {"picomatch", "@jest/core", "jest"}


def test_a_new_high_advisory_blocks():
    report = _report()
    report["vulnerabilities"]["picomatch"] = _vuln(
        "high", [_advisory("GHSA-0000-0000-0000")]
    )
    _accepted, blocking = gate.evaluate(report, {"GHSA-fc5q-39xc-vjpf"})
    assert "picomatch" in {name for name, _sev, _ids in blocking}


def test_critical_is_never_allowlisted():
    report = {"vulnerabilities": {"picomatch": _vuln("high", [_advisory("GHSA-x")])}}
    report["vulnerabilities"]["picomatch"]["severity"] = "critical"
    _accepted, blocking = gate.evaluate(report, {"GHSA-x"})
    assert [row[0] for row in blocking] == ["picomatch"]


def test_missing_vulnerabilities_blocks():
    _accepted, blocking = gate.evaluate({"error": "registry down"}, set())
    assert blocking == [("audit-report", "error", ["missing vulnerabilities"])]


def test_allowlist_ignores_comments_and_blanks(tmp_path):
    path = tmp_path / "allow.txt"
    path.write_text("# comment\nGHSA-fc5q-39xc-vjpf  # reason\n\n", encoding="utf-8")
    assert gate.load_allowlist(path) == {"GHSA-fc5q-39xc-vjpf"}


def test_allowlist_missing_file_is_empty(tmp_path):
    assert gate.load_allowlist(Path(tmp_path) / "missing.txt") == set()
