import json


def emit(payload, as_json, human=None):
    """Every command's single output path. JSON is the primary interface."""
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(human if human is not None else json.dumps(payload, indent=2, default=str))
