"""Example GRPO reward: penalize completions that stray from a target length."""

def reward(completions, target_len=200, **kwargs):
    return [-abs(len(c) - target_len) / target_len for c in completions]
