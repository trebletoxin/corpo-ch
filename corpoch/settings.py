import os
from dotenv import load_dotenv

load_dotenv('../')

from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "DiscordOauth2.settings")
