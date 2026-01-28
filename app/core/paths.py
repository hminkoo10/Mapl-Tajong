from pathlib import Path
import sys

APP_NAME = "MaplTajong"

def app_data_dir():
    base = Path.home() / "AppData" / "Roaming" / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base

def db_path():
    return app_data_dir() / "tajong.db"

def sounds_dir():
    d = app_data_dir() / "sounds"
    d.mkdir(parents=True, exist_ok=True)
    return d

def sound_file_path(file_name):
    return sounds_dir() / file_name

def app_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]

def asset_path(*parts):
    return app_root().joinpath("assets", *parts)
