import json
from pathlib import Path

from forge import recipes

REPO = Path(__file__).resolve().parents[1]


def test_talkie_recipes_valid():
    r = recipes.load_recipe(REPO / "recipes" / "talkie-1930to1980-qlora.yaml")
    assert r["method"] == "cpt-qlora"
    assert "talkie" in r["model_path"]
    f = recipes.load_recipe(REPO / "recipes" / "talkie-1930to1980-fsdp.yaml")
    assert f["profile"] in ("cuda-blackwell", "cuda-datacenter")


def test_boundary_evals_wellformed():
    lines = (REPO / "evals" / "talkie-1980-boundary.jsonl").read_text().splitlines()
    assert len(lines) >= 12
    cats = set()
    for ln in lines:
        e = json.loads(ln)
        assert {"prompt", "category", "expect"} <= set(e)
        assert e["category"] in {"knows-pre-1980", "refuses-post-1980", "hallucination-bait"}
        cats.add(e["category"])
    assert cats == {"knows-pre-1980", "refuses-post-1980", "hallucination-bait"}
