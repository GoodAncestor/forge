import json
import pytest
from forge import cli


def test_version_json(capsys):
    rc = cli.main(["--json", "version"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["name"] == "forge"
    assert "version" in out


def test_unknown_command_exits_nonzero():
    with pytest.raises(SystemExit):
        cli.main(["definitely-not-a-command"])


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("FORGE_DATA_CAP_TB", raising=False)
    import importlib
    from forge import config
    importlib.reload(config)
    assert config.DATA_CAP_TB == 20.0
    assert config.DATA_ROOT == "/mnt/models/datasets"
    assert config.FLEET_URL == "http://192.168.77.36:8096"
