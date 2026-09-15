"""模型包（Model Pack）保存与加载。

模型包 = joblib 二进制（预处理器 + 分类器） + JSON 元数据
（特征清单、标签映射、阈值、数据版本、依赖版本、训练参数）。
"""
from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib

ARTIFACT_EXT = ".pack_joblib"
META_EXT = ".pack_meta.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_model_pack(
    out_dir: str | Path,
    preprocessor,
    classifier,
    feature_list: list[str],
    label_map: dict,
    threshold: float | None,
    metadata: dict | None = None,
) -> str:
    """保存模型包，返回二进制文件路径。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    import sklearn  # noqa: F401  用于记录依赖版本

    meta = {
        "feature_list": feature_list,
        "label_map": label_map,
        "threshold": threshold,
        "dependency_versions": {
            "python": platform.python_version(),
            "scikit-learn": sklearn.__version__,
            "joblib": joblib.__version__,
        },
        "saved_at": _now_iso(),
        **(metadata or {}),
    }

    stem = (metadata or {}).get("name") or "model"
    joblib_path = out_dir / f"{stem}{ARTIFACT_EXT}"
    meta_path = out_dir / f"{stem}{META_EXT}"

    joblib.dump({"preprocessor": preprocessor, "classifier": classifier}, joblib_path)
    meta["artifact_hash"] = _sha256(joblib_path)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(joblib_path)


def load_model_pack(joblib_path: str | Path) -> dict:
    """加载模型包，返回含预处理器、分类器与全部元数据的字典。"""
    joblib_path = Path(joblib_path)
    data = joblib.load(joblib_path)
    meta_path = joblib_path.with_suffix(META_EXT)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return {
        "preprocessor": data["preprocessor"],
        "classifier": data["classifier"],
        "meta": meta,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
