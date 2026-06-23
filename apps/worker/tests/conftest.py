import sys
from pathlib import Path


WORKER_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKER_ROOT))

for module_name, module in list(sys.modules.items()):
    if module_name != "app" and not module_name.startswith("app."):
        continue
    app_file = getattr(module, "__file__", "")
    if app_file and not str(app_file).startswith(str(WORKER_ROOT)):
        sys.modules.pop(module_name, None)
