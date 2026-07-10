import os
import socket

FLEET_URL = os.environ.get("FORGE_FLEET_URL", "http://192.168.77.36:8096")
LEASE_SECRET = os.environ.get("FORGE_LEASE_SECRET", "")
DATA_ROOT = os.environ.get("FORGE_DATA_ROOT", "/mnt/models/datasets")
MODEL_ROOT = os.environ.get("FORGE_MODEL_ROOT", "/mnt/models")
DATA_CAP_TB = float(os.environ.get("FORGE_DATA_CAP_TB", "20"))
HOLDER = os.environ.get("FORGE_HOLDER", f"forge@{socket.gethostname()}")
