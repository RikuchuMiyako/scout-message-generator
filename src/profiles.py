"""企業プロファイルの読み込み・保存（JSON ファイルベース）。"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path

from .models import CompanyProfile

# リポジトリ直下の profiles/ ディレクトリ
PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


def _slugify(name: str) -> str:
    """企業名から安全なファイル名（拡張子なし）を生成する。"""
    slug = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE)
    return slug.strip("_") or "company"


def list_profiles() -> list[str]:
    """保存済みプロファイルの企業名一覧を返す。"""
    if not PROFILES_DIR.exists():
        return []
    names = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            names.append(data.get("company_name", path.stem))
        except (json.JSONDecodeError, OSError):
            continue
    return names


def _path_for(company_name: str) -> Path:
    return PROFILES_DIR / f"{_slugify(company_name)}.json"


def load_profile(company_name: str) -> CompanyProfile | None:
    """企業名からプロファイルを読み込む。見つからなければ None。"""
    path = _path_for(company_name)
    if not path.exists():
        # company_name 一致でも探す（slug 衝突対策）
        for p in PROFILES_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if data.get("company_name") == company_name:
                return CompanyProfile.from_dict(data)
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return CompanyProfile.from_dict(data)


def save_profile(profile: CompanyProfile) -> Path:
    """プロファイルを JSON として保存し、保存先パスを返す。"""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(profile.company_name)
    path.write_text(
        json.dumps(asdict(profile), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path
