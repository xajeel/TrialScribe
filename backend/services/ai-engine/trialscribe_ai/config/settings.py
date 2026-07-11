from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

CONFIG_DIR = Path(__file__).resolve().parent
ALLOWED_WEBSITES_FILE = CONFIG_DIR / "allowed_websites.yml"

MAX_RESULTS = int(os.getenv("MAX_RESULTS", "5"))
K_VALUE = int(os.getenv("K_value", "10"))
NUM_WORDS = int(os.getenv("NUM_WORDS", "500"))
