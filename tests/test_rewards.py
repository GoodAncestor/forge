import sys
from pathlib import Path

# rewards/ lives at the repo root, not under src/ — it's imported by the
# training entrypoints (forge/train/grpo.py) the same way: as a dotted path
# resolved with the repo root on sys.path (the runner execs the trainer
# subprocess with cwd=REPO_ROOT). Mirror that here rather than packaging
# rewards/ into the installed `forge` distribution.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rewards.length_penalty import reward  # noqa: E402


def test_reward_zero_at_target_length():
    assert reward(["x" * 200], target_len=200) == [0.0]


def test_reward_penalizes_deviation_symmetrically():
    short = reward(["x" * 100], target_len=200)[0]
    long = reward(["x" * 300], target_len=200)[0]
    assert short == long == -0.5


def test_reward_returns_one_score_per_completion():
    out = reward(["a", "bb", "ccc"], target_len=2)
    assert len(out) == 3
    assert all(v <= 0 for v in out)
