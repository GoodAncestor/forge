import signal
from pathlib import Path

import yaml

EXIT_OK, EXIT_JOB, EXIT_PAUSED = 0, 3, 75


class StopFlag:
    """SIGTERM handler shared by all entrypoints. The Trainer callback polls
    .triggered; the runner's SIGTERM therefore turns into save-and-stop."""

    def __init__(self):
        self.triggered = False

    def install(self):
        signal.signal(signal.SIGTERM, self._handle)

    def _handle(self, signum, frame):
        self.triggered = True


def latest_checkpoint(checkpoints_dir):
    d = Path(checkpoints_dir)
    if not d.exists():
        return None
    cks = sorted((c for c in d.iterdir()
                  if c.is_dir() and c.name.startswith("checkpoint-")),
                 key=lambda c: int(c.name.split("-")[1]))
    return cks[-1] if cks else None


def read_recipe(path):
    return yaml.safe_load(Path(path).read_text())


def render_tool_cmd(tool_cmd, recipe, run_dir, model_root):
    """Substitute forge's paths into an external tool's argv template.

    Shared by the surgery wrappers so both expose the same placeholders. In
    particular `{model_path}` is what lets one recipe's tool_cmd be reused
    across models instead of hardcoding a path into the argv — it resolves
    relative model_path values against model_root, and passes anything
    absolute (or an HF repo id, which most tools accept in the same slot)
    through untouched.
    """
    model_path = recipe.get("model_path") or ""
    if model_path and not Path(model_path).is_absolute() and "/" in model_path:
        # Relative NAS-style path, e.g. "talkie-lm/talkie-1930-13b-base".
        # A bare name with no slash is ambiguous with an HF repo id, so only
        # rewrite when it already looks like a path under the model root.
        candidate = Path(model_root) / model_path
        if candidate.exists():
            model_path = str(candidate)
    return [c.format(model_root=model_root, run_dir=run_dir,
                     model_path=model_path)
            for c in tool_cmd]


def make_stop_callback(flag):
    """Build the transformers TrainerCallback lazily (torch-free import)."""
    from transformers import TrainerCallback

    class SignalCheckpointCallback(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if flag.triggered:
                control.should_save = True
                control.should_training_stop = True
            return control

    return SignalCheckpointCallback()
