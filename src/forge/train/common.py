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
