"""Preflight must be honest while credentials are absent — that is the whole
point of the layer. These tests pin: missing creds are reported by name, a
CLI-on-PATH is required, provider config files substitute for env vars, and
nothing here ever touches the network."""
import pytest

from forge import cli, cloud, providers
from forge.providers.base import Credential, Provider


def test_registry_has_modal_and_azure():
    assert set(providers.PROVIDERS) == {"modal", "azure"}


def test_get_unknown_provider_names_the_known_ones():
    with pytest.raises(providers.UnknownProvider) as e:
        providers.get("lambda-labs")
    assert "modal" in str(e.value) and "azure" in str(e.value)


def test_modal_declares_eight_gpu_blackwell():
    """8-in-one-container is the reason Modal is the target for the big
    abliteration jobs; if this shape disappears the plan changes."""
    assert "B200:8" in providers.get("modal").gpus


def test_preflight_reports_missing_credentials_by_name(monkeypatch, tmp_path):
    """Regression: `satisfied_by` checks `Path(self.path).expanduser()` against
    the *real* filesystem, so this must not run against the real $HOME — a
    dev machine with a real ~/.modal.toml (exactly the environment this
    layer exists for) would otherwise flip `ok` to True and hide the bug."""
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/" + n)
    monkeypatch.setenv("HOME", str(tmp_path))
    r = providers.get("modal").preflight(env={})
    assert r["ok"] is False
    missing = {m["env"] for m in r["missing"]}
    assert {"MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"} <= missing
    # Optional credentials are not failures.
    assert "MODAL_PROFILE" not in missing


def test_preflight_ok_when_env_supplies_required_creds(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/" + n)
    r = providers.get("modal").preflight(
        env={"MODAL_TOKEN_ID": "id", "MODAL_TOKEN_SECRET": "sec"})
    assert r["ok"] is True
    assert r["missing"] == []
    assert r["resolved"]["MODAL_TOKEN_ID"] == "env"


def test_config_file_satisfies_credential_without_env(tmp_path, monkeypatch):
    """`modal token new` writes a token file and exports nothing; reporting
    that as missing would send the operator chasing a non-problem."""
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/" + n)
    tok = tmp_path / "modal.toml"
    tok.write_text("[default]\n")

    class P(Provider):
        name = "p"
        credentials = (Credential("X_TOK", "d", path=str(tok)),)

    r = P().preflight(env={})
    assert r["ok"] is True
    assert r["resolved"]["X_TOK"] == "file"


def test_missing_cli_blocks_ok_and_offers_install(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda n: None)
    r = providers.get("modal").preflight(
        env={"MODAL_TOKEN_ID": "id", "MODAL_TOKEN_SECRET": "sec"})
    assert r["ok"] is False
    assert r["cli"]["ok"] is False
    assert "modal token new" in r["cli"]["install"]


def test_preflight_exits_zero_even_when_not_ready(monkeypatch, capsys):
    """Run before the credentials exist, a red report is information, not a
    failed command — a nonzero exit here would break any wrapper that checks."""
    monkeypatch.setattr("shutil.which", lambda n: None)
    monkeypatch.setattr("os.environ", {})
    rc = cli.main(["--json", "cloud", "preflight"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "MODAL_TOKEN_ID" in out and "AZURE_SUBSCRIPTION_ID" in out


def test_preflight_unknown_provider_is_refused(capsys):
    assert cli.main(["--json", "cloud", "preflight", "--provider", "nope"]) == 2


def test_providers_command_lists_gpu_shapes(capsys):
    assert cli.main(["cloud", "providers"]) == 0
    out = capsys.readouterr().out
    assert "modal" in out and "azure" in out and "B200:8" in out


def test_human_preflight_marks_missing_lines(monkeypatch, tmp_path):
    """Same real-$HOME leak as test_preflight_reports_missing_credentials_by_name,
    for Azure's ~/.azure path credential."""
    monkeypatch.setattr("shutil.which", lambda n: None)
    monkeypatch.setenv("HOME", str(tmp_path))
    text = cloud._human_preflight(providers.get("azure").preflight(env={}))
    assert "NOT READY" in text
    assert "MISSING  AZURE_SUBSCRIPTION_ID" in text


def test_bare_azure_dir_does_not_satisfy_credential(monkeypatch, tmp_path):
    """`az --version` (and any other `az` invocation) creates ~/.azure/ for
    telemetry/config even without a login — that must NOT read as ready.
    Only a real `az login` artifact (azureProfile.json) should."""
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/" + n)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure" / "config").write_text("[core]\n")

    r = providers.get("azure").preflight(env={})
    assert r["ok"] is False
    missing = {m["env"] for m in r["missing"]}
    assert {"AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID"} <= missing


def test_azure_login_profile_satisfies_credential(monkeypatch, tmp_path):
    """A real `az login` writes ~/.azure/azureProfile.json; that should
    satisfy the credential without env vars, same as Modal's token file."""
    monkeypatch.setattr("shutil.which", lambda n: "/usr/bin/" + n)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".azure").mkdir()
    (tmp_path / ".azure" / "azureProfile.json").write_text("{}")

    r = providers.get("azure").preflight(env={})
    assert r["ok"] is True
    assert r["resolved"]["AZURE_SUBSCRIPTION_ID"] == "file"
    assert r["resolved"]["AZURE_TENANT_ID"] == "file"
