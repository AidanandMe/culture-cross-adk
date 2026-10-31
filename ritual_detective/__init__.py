from pathlib import Path
from dotenv import load_dotenv

# Always load .env from project root with override=True so the .env API key is used
_project_root_env = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_project_root_env, override=True)

from . import agent  # noqa: E402, F401
