import pytest

from forge import data


class Sib:
    def __init__(self, size):
        self.size = size


class FakeResponse:
    def raise_for_status(self):
        pass


class FakeApi:
    def __init__(self, *a, **k):
        pass

    def dataset_info(self, repo_id, files_metadata=False):
        assert files_metadata
        class Info:
            siblings = [Sib(100), Sib(250), Sib(None)]
        return Info()

    def model_info(self, repo_id, files_metadata=False):
        class Info:
            siblings = [Sib(7)]
        return Info()


def test_measure_hf_dataset(monkeypatch):
    monkeypatch.setattr(data, "HfApi", FakeApi)
    e = {"name": "x", "source": "hf://org/name", "nas_path": "x/"}
    assert data.measure_entry(e) == 350


def test_measure_hf_model_repo(monkeypatch):
    monkeypatch.setattr(data, "HfApi", FakeApi)
    e = {"name": "x", "source": "hf://org/name", "nas_path": "x/",
         "notes": "", "repo_type": "model"}
    assert data.measure_entry(e) == 7


def test_measure_url_head(monkeypatch):
    class R(FakeResponse):
        headers = {"Content-Length": "12345"}
    monkeypatch.setattr(data.requests, "head", lambda *a, **k: R())
    e = {"name": "x", "source": "url://https://example.org/f.bz2", "nas_path": "x/"}
    assert data.measure_entry(e) == 12345


def test_measure_url_error_status_rejected(monkeypatch):
    import requests as req

    class R(FakeResponse):
        headers = {"Content-Length": "135"}
        def raise_for_status(self):
            raise req.HTTPError("403 Client Error")
    monkeypatch.setattr(data.requests, "head", lambda *a, **k: R())
    e = {"name": "x", "source": "url://https://example.org/f.bz2", "nas_path": "x/"}
    with pytest.raises(req.HTTPError):
        data.measure_entry(e)


def test_measure_rsync_source_returns_none():
    e = {"name": "x", "source": "url://rsync://host/mod", "nas_path": "x/"}
    assert data.measure_entry(e) is None
