import shutil

import yaml

from profileos.validate import public_url_problem, validate


def test_real_data_is_valid(repo_copy):
    assert validate(repo_copy).ok


def _edit(root, name, fn):
    p = root / "data" / f"{name}.yml"
    d = yaml.safe_load(p.read_text())
    fn(d)
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))


def test_bad_status_fails(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["UsageOS"].update(status="running"))
    assert any("status" in e for e in validate(repo_copy).errors)


def test_verified_requires_tagline_and_stack(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["NetOS"].update(verified=True))
    assert any("verified" in e for e in validate(repo_copy).errors)


def test_published_fields_need_publishable_evidence(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["NetOS"].update(tagline="Invented tagline"))
    assert any("no evidence record" in e for e in validate(repo_copy).errors)


def test_low_confidence_is_never_publishable(repo_copy):
    def low(d):
        d["projects"]["UsageOS"]["tagline"]["confidence"] = "LOW"
    _edit(repo_copy, "evidence", low)
    assert any("not publishable" in e for e in validate(repo_copy).errors)


def test_published_value_must_match_its_evidence(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["UsageOS"].update(tagline="Something else entirely"))
    assert any("differs from its evidence" in e for e in validate(repo_copy).errors)


def test_stack_items_need_evidence(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["UsageOS"]["stack"].append("Kubernetes"))
    assert any("Kubernetes" in e for e in validate(repo_copy).errors)


def test_secret_like_keys_rejected(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["UsageOS"].update(api_token="x"))
    assert not validate(repo_copy).ok


def test_unknown_relation_and_alias_targets(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["UsageOS"].update(relations=[{"from": "UsageOS", "to": "Nope"}]))
    _edit(repo_copy, "aliases", lambda d: d["aliases"].update(ghost="Missing"))
    errs = " ".join(validate(repo_copy).errors)
    assert "Nope" in errs and "Missing" in errs


def test_tagline_length_limit(repo_copy):
    _edit(repo_copy, "projects", lambda d: d["UsageOS"].update(tagline="x" * 91))
    assert not validate(repo_copy).ok


def test_health_url_ssrf_rules():
    for bad in ("http://example.com", "https://localhost/x", "https://10.0.0.5/h", "https://svc.internal/h", "https://example.com/h?token=1"):
        assert public_url_problem(bad), bad
    assert public_url_problem("https://example.com/health") is None


def test_missing_marker_in_readme_fails(repo_copy):
    p = repo_copy / "README.md"
    p.write_text(p.read_text().replace("<!-- PROFILEOS:END:PULSE -->", ""))
    assert any("PULSE" in e for e in validate(repo_copy).errors)


def test_stack_without_evidence_warns_and_strict_errors(repo_copy):
    assert any("no evidence" in w for w in validate(repo_copy).warnings)
    assert not validate(repo_copy, strict=True).ok
