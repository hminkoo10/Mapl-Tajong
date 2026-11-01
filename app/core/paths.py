import os
from pathlib import Path
import sys

APP_NAME = "MaplTajong"

# 통합 클라우드가 정해 주는 폴더 (main.py 에서 configure 로 맞춘다)
#   _sync_dir  : 같은 계정이면 모든 기기가 같은 내용 (config.json, state.json, sounds/, logs/)
#   _local_dir : 이 컴퓨터에만 두는 것 (tajong.db, 잠금 파일, 캐시, 로그 등)
_sync_dir = None
_local_dir = None


def configure(data_dir, local_dir):
    global _sync_dir, _local_dir
    _sync_dir = Path(data_dir)
    _local_dir = Path(local_dir)


def legacy_data_dir():
    """예전에 따로 설치해 쓰던 프로그램의 데이터 폴더 (%APPDATA%\\MaplTajong). 만들지 않는다."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / APP_NAME


def app_data_dir():
    base = _local_dir if _local_dir is not None else legacy_data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base


def sync_dir():
    base = _sync_dir if _sync_dir is not None else app_data_dir()
    base.mkdir(parents=True, exist_ok=True)
    return base

def db_path():
    return app_data_dir() / "tajong.db"

def sounds_dir():
    d = sync_dir() / "sounds"
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

def base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]

def amp_cache_dir():
    d = app_data_dir() / "amp_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d

def resource_path(*parts):
    return base_dir().joinpath(*parts)

def _sub_dir(name):
    d = app_data_dir() / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_tmp_dir():
    return _sub_dir("downloads")


def originals_dir():
    return _sub_dir("originals")


def ui_cache_dir():
    return _sub_dir("ui_cache")


def temp_dir():
    return _sub_dir("tmp")


def backups_dir():
    return _sub_dir("backups")
