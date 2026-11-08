"""weight_source preflight: HF API fully mocked; no network, no writes."""
import json

import pytest

from forge import cli, weights


class Resp:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body or {}

    def json(self):
        return self._b


def fine_grained(perms):
    return {"auth": {"accessToken": {"role": "fineGrained",
            "fineGrained": {"scoped": [{"permissions": perms}]}}}}


def fake_get(routes, calls=None):
    def get(url, headers=None, timeout=None):
        if calls is not None:
            calls.append((url, dict(headers or {})))
        for suffix, resp in routes.items():
            if url.endswith(suffix):
                return resp
        return Resp(404)
    return get


ENV = {"HF_TOKEN": "hf_dummy"}
PRIV = weights.WeightSource("private-hf", "GoodAncestor/tuned", "main")
PUB = weights.WeightSource("hf", "zai-org/GLM-5.2", "main")


def test_parse_forms():
    assert weights.parse("hf:a/b") == weights.WeightSource("hf", "a/b", "main")
    assert weights.parse("private-hf:a/b@v2").revision == "v2"


@pytest.mark.parametrize("bad", ["", "a/b", "s3:a/b", "hf:nodash", "hf:a/b/c", "hf:/b"])
def test_parse_rejects(bad):
    with pytest.raises(weights.BadWeightSpec):
        weights.parse(bad)


def test_private_ok(monkeypatch):
    monkeypatch.setattr(weights, "TOKEN_FILE", "/nonexistent")
    g = fake_get({"whoami-v2": Resp(200, fine_grained(["repo.content.read"])),
                  "revision/main": Resp(200, {"private": True})})
    r = weights.preflight(PRIV, env=ENV, get=g)
    assert r["ok"] and r["token"] == "env:HF_TOKEN"


def test_private_missing_scope(monkeypatch):
    g = fake_get({"whoami-v2": Resp(200, fine_grained(["repo.write"]))})
    r = weights.preflight(PRIV, env=ENV, get=g)
    assert not r["ok"] and "lacks repo.content.read" in r["checks"]["repo.content.read"]


def test_private_without_token_makes_no_calls(monkeypatch, tmp_path):
    monkeypatch.setattr(weights, "TOKEN_FILE", str(tmp_path / "none"))
    calls = []
    r = weights.preflight(PRIV, env={}, get=fake_get({}, calls))
    assert not r["ok"] and calls == []


def test_private_kind_but_public_repo_is_flagged():
    g = fake_get({"whoami-v2": Resp(200, fine_grained(["repo.content.read"])),
                  "revision/main": Resp(200, {"private": False})})
    r = weights.preflight(PRIV, env=ENV, get=g)
    assert not r["ok"] and "private" in r["checks"]


def test_bad_token_stops_at_whoami():
    g = fake_get({"whoami-v2": Resp(401)})
    r = weights.preflight(PUB, env=ENV, get=g)
    assert not r["ok"] and r["checks"]["whoami"] == "http 401"


def test_public_repo_without_token(monkeypatch, tmp_path):
    monkeypatch.setattr(weights, "TOKEN_FILE", str(tmp_path / "none"))
    g = fake_get({"revision/main": Resp(200, {"private": False})})
    assert weights.preflight(PUB, env={}, get=g)["ok"]


def test_missing_repo_is_404_not_crash():
    g = fake_get({"whoami-v2": Resp(200, {}), })
    r = weights.preflight(PUB, env=ENV, get=g)
    assert not r["ok"] and "not found" in r["checks"]["repo"]


def test_only_get_requests_and_token_never_in_output():
    calls = []
    g = fake_get({"whoami-v2": Resp(200, fine_grained(["repo.content.read"])),
                  "revision/main": Resp(200, {"private": True})}, calls)
    r = weights.preflight(PRIV, env=ENV, get=g)
    assert "hf_dummy" not in json.dumps(r)
    assert all(u.startswith(weights.HF_API) for u, _ in calls)


def test_cli_without_flag_reports_not_requested(capsys):
    assert cli.main(["--json", "cloud", "preflight"]) == 0
    assert json.loads(capsys.readouterr().out)["weight_source"] == {"status": "not_requested"}


def test_cli_bad_spec_refused(capsys):
    assert cli.main(["--json", "cloud", "preflight", "--weight-source", "nope"]) == 2


def test_cli_with_flag_includes_status(monkeypatch, capsys):
    monkeypatch.setattr(weights, "preflight",
                        lambda s: {"ok": True, "checks": {}, **s.describe()})
    assert cli.main(["--json", "cloud", "preflight", "--weight-source", "hf:a/b"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["weight_source"]["status"] == "ready"
    assert out["weight_source"]["repo"] == "a/b"
