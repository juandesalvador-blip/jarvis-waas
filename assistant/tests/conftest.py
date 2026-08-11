import sys
from pathlib import Path

# Permite "import crew" / "import app" sin importar desde dónde se ejecute pytest.
ASSISTANT_DIR = Path(__file__).resolve().parent.parent
if str(ASSISTANT_DIR) not in sys.path:
    sys.path.insert(0, str(ASSISTANT_DIR))
