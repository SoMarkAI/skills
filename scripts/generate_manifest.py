import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = REPO_ROOT / "skills"
MANIFEST_PATH = REPO_ROOT / "manifest.json"
DEFAULT_SOURCE = "https://github.com/SoMarkAI/skills"


def sha256_file(file_path: Path) -> str:
    """
    计算文件的SHA256哈希值
    :param file_path: 文件路径
    :return: 文件的SHA256哈希值
    """
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    """
    获取当前UTC时间的ISO格式字符串
    :return: 当前UTC时间的ISO格式字符串
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def load_meta(skill_dir: Path) -> dict[str, Any]:
    """
    加载skill目录的_meta.json文件
    :param skill_dir: skill目录路径
    :return: 包含slug和version的字典
    """
    meta_path = skill_dir / "_meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"缺少 _meta.json: {skill_dir}")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"_meta.json 不是合法 JSON: {meta_path}") from exc

    slug = meta.get("slug")
    version = meta.get("version")
    if not isinstance(slug, str) or not slug.strip():
        raise ValueError(f"_meta.json 缺少有效 slug: {meta_path}")
    if not isinstance(version, str) or not version.strip():
        raise ValueError(f"_meta.json 缺少有效 version: {meta_path}")

    return {"slug": slug.strip(), "version": version.strip()}


def iter_skill_files(skill_dir: Path) -> list[Path]:
    """
    遍历skill目录下的所有文件
    :param skill_dir: skill目录路径
    :return: 包含所有文件路径的列表，按文件名排序
    """
    return sorted(
        [path for path in skill_dir.iterdir() if path.is_file()],
        key=lambda path: path.name,
    )


def build_skill_entry(repo_root: Path, skill_dir: Path) -> tuple[str, dict[str, Any]]:
    """
    构建skill目录的manifest.json条目
    :param repo_root: 仓库根目录
    :param skill_dir: skill目录路径
    :return: 包含slug和manifest.json条目的元组，slug为_meta.json中的slug，manifest.json条目包含version、path和files字段
    """
    meta = load_meta(skill_dir)
    files: dict[str, dict[str, str]] = {}

    for file_path in iter_skill_files(skill_dir):
        files[file_path.name] = {"sha256": sha256_file(file_path)}

    relative_path = skill_dir.relative_to(repo_root).as_posix()
    return meta["slug"], {
        "version": meta["version"],
        "path": relative_path,
        "files": files,
    }


def build_manifest(repo_root: Path, skills_dir: Path, source: str) -> dict[str, Any]:
    """
    构建manifest.json文件
    :param repo_root: 仓库根目录
    :param skills_dir: skills目录路径
    :param source: manifest source 字段
    :return: 包含schema、source、generated_at和skills字段的字典
    """
    if not skills_dir.exists() or not skills_dir.is_dir():
        raise FileNotFoundError(f"skills 目录不存在: {skills_dir}")

    skills: dict[str, dict[str, Any]] = {}
    for skill_dir in sorted(
            [path for path in skills_dir.iterdir() if path.is_dir()],
            key=lambda path: path.name,
    ):
        slug, entry = build_skill_entry(repo_root, skill_dir)
        if slug in skills:
            raise ValueError(f"重复的 skill slug: {slug}")
        skills[slug] = entry

    return {
        "schema": 1,
        "source": source,
        "generated_at": utc_now(),
        "skills": skills,
    }


def main() -> None:
    manifest = build_manifest(REPO_ROOT, SKILLS_DIR, DEFAULT_SOURCE)
    rendered = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    MANIFEST_PATH.write_text(rendered, encoding="utf-8")
    print(f"manifest 已生成: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
