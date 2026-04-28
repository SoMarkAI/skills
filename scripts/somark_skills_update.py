from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

LOCK_FILENAME = ".somark-skills.lock.json"  # 锁文件名
BACKUP_DIRNAME = ".somark-skills-backups"  # 备份目录名
DEFAULT_SOURCE = "https://github.com/SoMarkAI/skills"  # 默认skill仓库地址
MANIFEST_URL = "https://raw.githubusercontent.com/SoMarkAI/skills/refs/heads/lty/feat/skill-auto-update/manifest.json"
RAW_BASE_URL = "https://raw.githubusercontent.com/SoMarkAI/skills/refs/heads/lty/feat/skill-auto-update"

def sha256_file(file_path: Path) -> str:
    """
    计算文件的SHA256哈希值
    :param file_path: 文件路径
    :return: 文件的SHA256哈希值
    """
    h = hashlib.sha256()  # 创建一个 SHA-256 哈希计算对象
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(content: bytes) -> str:
    """
    计算字节内容的SHA256哈希值
    :param content: 字节内容
    :return: SHA256哈希值
    """
    h = hashlib.sha256()
    h.update(content)
    return h.hexdigest()


def utc_now() -> str:
    """
    获取当前UTC时间的ISO格式字符串
    :return: 当前UTC时间的ISO格式字符串
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def generate_lock(install_dir: Path, source: str = DEFAULT_SOURCE) -> dict:
    """
    生成锁文件内容
    :param install_dir: 安装目录
    :param source: skill仓库地址，默认值为 DEFAULT_SOURCE
    :return: 锁文件内容
    """
    skills: dict[str, dict[str, Any]] = {}

    for skill_dir in sorted(install_dir.iterdir(), key=lambda path: path.name):
        if not skill_dir.is_dir():
            continue

        meta_path = skill_dir / "_meta.json"
        if not meta_path.exists():
            continue

        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        slug = meta.get("slug")
        version = meta.get("version")

        if not isinstance(slug, str) or not slug.strip():
            raise ValueError(f"_meta.json 缺少有效 slug: {meta_path}")
        if not isinstance(version, str) or not version.strip():
            raise ValueError(f"_meta.json 缺少有效 version: {meta_path}")

        files: dict[str, dict[str, str]] = {}

        for file_path in sorted(skill_dir.iterdir(), key=lambda path: path.name):
            if not file_path.is_file():
                continue

            files[file_path.name] = {"sha256": sha256_file(file_path)}

        skills[slug.strip()] = {
            "version": version,
            "path": skill_dir.name,
            "files": files,
        }
    return {
        "schema": 1,
        "source": source,
        "generated_at": utc_now(),
        "skills": skills,
    }


def read_lock(install_dir: Path) -> dict | None:
    """
    读取锁文件内容
    :param install_dir: 安装目录
    :return: 锁文件内容，如果文件不存在则返回 None
    """
    lock_path = install_dir / LOCK_FILENAME

    if not lock_path.exists():
        return None

    return json.loads(lock_path.read_text(encoding="utf-8"))


def write_lock(install_dir: Path, lock: dict) -> None:
    """
    写入锁文件内容
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :return: None
    """
    lock_path = install_dir / LOCK_FILENAME
    lock_path.write_text(
        json.dumps(lock, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def file_was_modified(local_file: Path, locked_sha256: str) -> bool:
    """
    检查本地文件是否被修改
    :param local_file: 本地文件路径
    :param locked_sha256: 锁文件中记录的SHA256哈希值
    :return: 如果本地文件被修改则返回 True，否则返回 False
    """
    if not local_file.is_file():
        return True

    return sha256_file(local_file) != locked_sha256


def find_local_changes(install_dir: Path, lock: dict[str, Any]) -> List[str]:
    """
    查找本地修改的文件
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :return: 本地修改的文件列表
    """
    changes = []
    for slug, skill_info in lock["skills"].items():
        skill_dir = install_dir / skill_info["path"]

        for filename, file_info in skill_info["files"].items():
            local_file = skill_dir / filename
            locked_sha256 = file_info["sha256"]

            if file_was_modified(local_file, locked_sha256):
                changes.append(f"{slug}/{filename}")
    return changes


def read_manifest(manifest_path: Path) -> dict[str, Any]:
    """
    读取skill仓库的manifest.json内容
    :param manifest_path: manifest.json文件路径
    :return: manifest.json内容
    """
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json 不存在: {manifest_path}")

    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifest.json 不是合法 JSON: {manifest_path}") from exc


def download_bytes(url: str, timeout: int = 20) -> bytes:
    """
    下载远端文件字节内容
    :param url: 下载地址
    :param timeout: 超时时间（秒）
    :return: 文件字节内容
    """
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "somark-skills-updater"},
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"下载失败: {url}, HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"下载失败: {url}, reason={exc.reason}") from exc


def download_manifest(url: str = MANIFEST_URL) -> dict[str, Any]:
    """
    从远端下载 manifest.json
    :param url: manifest 下载地址
    :return: manifest.json内容
    """
    content = download_bytes(url)

    try:
        return json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"远端 manifest 不是合法 JSON: {url}") from exc


def parse_version(version: str) -> tuple[int, ...]:
    """
    解析版本号，例如:
    0.1.2 -> (0, 1, 2)
    只支持纯数字版本号，不支持 1.0.0-beta.1。
    :param version: 版本号字符串
    :return: 版本号元组，例如 (0, 1, 2)
    """
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError as exc:
        raise ValueError(f"不支持的版本号格式: {version}") from exc


def remote_is_newer(local_version: str, remote_version: str) -> bool:
    """
    检查远程版本是否新于本地版本
    :param local_version: 本地版本号字符串
    :param remote_version: 远远程版本号字符串
    :return: 如果远程版本新于本地版本则返回 True，否则返回 False
    """
    local_version_tuple = parse_version(local_version)
    remote_version_tuple = parse_version(remote_version)

    return remote_version_tuple > local_version_tuple


def find_updates(
        lock: dict[str, Any],
        manifest: dict[str, Any],
        include_not_installed: bool = False,
) -> List[dict[str, str]]:
    """
    比较本地 lock 和远端 manifest，找出需要更新的 skill
    :param lock: 锁文件内容
    :param manifest: manifest.json内容
    :param include_not_installed: 是否将未安装的 skill 纳入更新
    :return: 需要更新的 skill 列表
    """
    updates: list[dict[str, str]] = []

    local_skills = lock.get("skills", {})
    remote_skills = manifest.get("skills", {})

    if not isinstance(local_skills, dict):
        raise ValueError("lock 中的 skills 字段必须是对象")
    if not isinstance(remote_skills, dict):
        raise ValueError("manifest 中的 skills 字段必须是对象")

    for slug, remote_info in remote_skills.items():
        if not isinstance(remote_info, dict):
            raise ValueError(f"manifest 中 skill 信息无效: {slug}")

        remote_version = remote_info.get("version")
        if not isinstance(remote_version, str) or not remote_version.strip():
            raise ValueError(f"manifest 中缺少有效 version: {slug}")

        local_info = local_skills.get(slug)

        if local_info is None:
            if not include_not_installed:
                continue
            updates.append({
                "slug": slug,
                "reason": "not_installed",
                "local_version": "",
                "remote_version": remote_version.strip(),

            })
            continue
        if not isinstance(local_info, dict):
            raise ValueError(f"lock 中 skill 信息无效: {slug}")

        local_version = local_info.get("version")
        if not isinstance(local_version, str) or not local_version.strip():
            raise ValueError(f"lock 中缺少有效 version: {slug}")

        local_version = local_version.strip()

        remote_version = remote_version.strip()

        if remote_is_newer(local_version, remote_version):
            updates.append({
                "slug": slug,
                "reason": "newer_version",
                "local_version": local_version,
                "remote_version": remote_version,
            })

    return updates


def find_modified_files(
        install_dir: Path,
        lock: dict[str, Any],
        slug: str,
) -> list[str]:
    """
    检查某个 skill 的本地文件是否被用户修改。
    返回被修改的文件列表。
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :param slug: skill slug
    :return: 被修改的文件列表
    """
    skills = lock.get("skills", {})
    if not isinstance(skills, dict):
        raise ValueError("lock 中的 skills 字段必须是对象")

    skill_info = skills.get(slug)
    if not isinstance(skill_info, dict):
        raise ValueError(f"lock 中不存在 skill: {slug}")

    skill_path = skill_info.get("path")
    if not isinstance(skill_path, str) or not skill_path.strip():
        raise ValueError(f"lock 中 skill 缺少有效 path: {slug}")

    files = skill_info.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"lock 中 skill files 字段必须是对象: {slug}")

    modified: list[str] = []
    skill_dir = install_dir / skill_path

    for filename, file_info in files.items():
        if not isinstance(file_info, dict):
            raise ValueError(f"lock 中文件信息无效: {slug}/{filename}")

        locked_sha256 = file_info.get("sha256")
        if not isinstance(locked_sha256, str) or not locked_sha256.strip():
            raise ValueError(f"lock 中文件缺少 sha256: {slug}/{filename}")

        local_file = skill_dir / filename

        if file_was_modified(local_file, locked_sha256):
            modified.append(filename)

    return modified


def classify_updates_by_local_changes(
        install_dir: Path,
        lock: dict[str, Any],
        updates: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """
    把更新列表分成:
    - safe_updates: 本地未修改，可以自动更新
    - skipped_updates: 本地有修改，跳过
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :param updates: 需要更新的 skill 列表
    :return: safe_updates, skipped_updates
    """
    safe_updates: list[dict[str, str]] = []
    skipped_updates: list[dict[str, Any]] = []

    for update in updates:
        slug = update["slug"]

        # 未安装的 skill 没有本地文件冲突，可以后续作为安装处理。
        if update["reason"] == "not_installed":
            safe_updates.append(update)
            continue

        modified_files = find_modified_files(
            install_dir=install_dir,
            lock=lock,
            slug=slug,
        )

        if modified_files:
            skipped_updates.append(
                {
                    **update,
                    "modified_files": modified_files,
                }
            )
        else:
            safe_updates.append(update)

    return safe_updates, skipped_updates


def get_manifest_skill(manifest: dict[str, Any], slug: str) -> dict[str, Any]:
    """
    从 manifest 中获取某个 skill 的远端信息
    :param manifest: manifest.json内容
    :param slug: skill slug
    :return: skill 远端信息
    """
    skills = manifest.get("skills", {})
    if not isinstance(skills, dict):
        raise ValueError("manifest 中的 skills 字段必须是对象")

    skill_info = skills.get(slug)
    if not isinstance(skill_info, dict):
        raise ValueError(f"manifest 中不存在 skill: {slug}")

    return skill_info


def read_remote_file_from_repo(
        repo_root: Path,
        manifest_skill: dict[str, Any],
        filename: str,
) -> bytes:
    """
    从当前仓库读取远端文件内容。MVP 阶段用本地仓库模拟远端仓库。
    :param repo_root: 仓库根目录
    :param manifest_skill: manifest 中某个 skill 的信息
    :param filename: 文件名
    :return: 文件字节内容
    """
    skill_path = manifest_skill.get("path")
    if not isinstance(skill_path, str) or not skill_path.strip():
        raise ValueError("manifest skill 缺少有效 path")

    file_path = repo_root / skill_path / filename
    if not file_path.is_file():
        raise FileNotFoundError(f"远端文件不存在: {file_path}")

    return file_path.read_bytes()


def download_remote_file(
        manifest_skill: dict[str, Any],
        filename: str,
) -> bytes:
    """
    从 GitHub raw 下载远端 skill 文件。
    :param manifest_skill: manifest 中某个 skill 的信息
    :param filename: 文件名
    :return: 文件字节内容
    """
    skill_path = manifest_skill.get("path")
    if not isinstance(skill_path, str) or not skill_path.strip():
        raise ValueError("manifest skill 缺少有效 path")

    url = f"{RAW_BASE_URL}/{skill_path}/{filename}"
    return download_bytes(url)


def verify_update_files(
        manifest: dict[str, Any],
        update: dict[str, str],
) -> dict[str, bytes]:
    """
    读取并校验某个待更新 skill 的所有远端文件。
    返回 filename -> bytes。
    :param manifest: manifest.json内容
    :param update: 待更新 skill 信息
    :return: 已校验文件内容
    """
    slug = update["slug"]
    manifest_skill = get_manifest_skill(manifest, slug)

    files = manifest_skill.get("files", {})
    if not isinstance(files, dict):
        raise ValueError(f"manifest 中 skill files 字段必须是对象: {slug}")

    verified_files: dict[str, bytes] = {}

    for filename, file_info in files.items():
        if not isinstance(file_info, dict):
            raise ValueError(f"manifest 中文件信息无效: {slug}/{filename}")

        expected_sha256 = file_info.get("sha256")
        if not isinstance(expected_sha256, str) or not expected_sha256.strip():
            raise ValueError(f"manifest 中文件缺少 sha256: {slug}/{filename}")

        content = download_remote_file(manifest_skill=manifest_skill, filename=filename)

        actual_sha256 = sha256_bytes(content)
        if actual_sha256 != expected_sha256:
            raise ValueError(
                f"sha256 校验失败: {slug}/{filename}, "
                f"expected={expected_sha256}, actual={actual_sha256}"
            )

        verified_files[filename] = content

    return verified_files


def verify_safe_updates(
        manifest: dict[str, Any],
        safe_updates: list[dict[str, str]],
) -> dict[str, dict[str, bytes]]:
    """
    校验所有允许自动更新的 skill 文件。
    :param manifest: manifest.json内容
    :param safe_updates: 本地未修改、允许自动更新的 skill 列表
    :return: slug -> filename -> bytes
    """
    verified: dict[str, dict[str, bytes]] = {}

    for update in safe_updates:
        slug = update["slug"]
        verified[slug] = verify_update_files(
            manifest=manifest,
            update=update,
        )

    return verified


def get_local_skill_dir(
        install_dir: Path,
        lock: dict[str, Any],
        slug: str,
) -> Path:
    """
    获取某个 skill 的本地安装目录。未安装的 skill 默认安装到 install_dir / slug。
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :param slug: skill slug
    :return: skill 本地目录
    """
    skills = lock.get("skills", {})
    if not isinstance(skills, dict):
        raise ValueError("lock 中的 skills 字段必须是对象")

    skill_info = skills.get(slug)
    if skill_info is None:
        return install_dir / slug
    if not isinstance(skill_info, dict):
        raise ValueError(f"lock 中 skill 信息无效: {slug}")

    skill_path = skill_info.get("path")
    if not isinstance(skill_path, str) or not skill_path.strip():
        raise ValueError(f"lock 中 skill 缺少有效 path: {slug}")

    return install_dir / skill_path


def backup_skill(
        install_dir: Path,
        lock: dict[str, Any],
        slug: str,
) -> Path | None:
    """
    备份某个本地 skill。未安装的 skill 不需要备份。
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :param slug: skill slug
    :return: 备份目录；如果本地目录不存在则返回 None
    """
    skill_dir = get_local_skill_dir(install_dir, lock, slug)
    if not skill_dir.exists():
        return None

    backup_root = install_dir / BACKUP_DIRNAME
    backup_root.mkdir(parents=True, exist_ok=True)

    timestamp = utc_now().replace(":", "").replace("-", "")
    backup_dir = backup_root / f"{slug}-{timestamp}"
    shutil.copytree(skill_dir, backup_dir)

    return backup_dir


def write_verified_files(skill_dir: Path, files: dict[str, bytes]) -> None:
    """
    将已通过 sha256 校验的文件写入本地 skill 目录。
    :param skill_dir: skill 本地目录
    :param files: filename -> bytes
    :return: None
    """
    skill_dir.mkdir(parents=True, exist_ok=True)

    for filename, content in files.items():
        target_path = skill_dir / filename
        tmp_path = skill_dir / f".{filename}.tmp"
        tmp_path.write_bytes(content)
        tmp_path.replace(target_path)


def restore_backup(skill_dir: Path, backup_dir: Path | None) -> None:
    """
    从备份恢复本地 skill。
    :param skill_dir: skill 本地目录
    :param backup_dir: 备份目录
    :return: None
    """
    if backup_dir is None:
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        return

    if skill_dir.exists():
        shutil.rmtree(skill_dir)

    shutil.copytree(backup_dir, skill_dir)


def apply_update(
        install_dir: Path,
        lock: dict[str, Any],
        slug: str,
        files: dict[str, bytes],
) -> None:
    """
    应用单个 skill 更新。写入失败时回滚到备份。
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :param slug: skill slug
    :param files: 已校验文件内容
    :return: None
    """
    skill_dir = get_local_skill_dir(install_dir, lock, slug)
    backup_dir = backup_skill(install_dir, lock, slug)

    try:
        write_verified_files(skill_dir, files)
    except Exception:
        restore_backup(skill_dir, backup_dir)
        raise


def apply_verified_updates(
        install_dir: Path,
        lock: dict[str, Any],
        verified_updates: dict[str, dict[str, bytes]],
) -> None:
    """
    批量应用已通过校验的 skill 更新。
    :param install_dir: 安装目录
    :param lock: 锁文件内容
    :param verified_updates: slug -> filename -> bytes
    :return: None
    """
    for slug, files in verified_updates.items():
        apply_update(
            install_dir=install_dir,
            lock=lock,
            slug=slug,
            files=files,
        )
        print(f"{slug}: 更新完成")


def print_update_plan(
        safe_updates: list[dict[str, str]],
        skipped_updates: list[dict[str, Any]],
) -> None:
    """
    打印更新计划
    :param safe_updates: 可以自动更新的 skill 列表
    :param skipped_updates: 因本地修改而跳过的 skill 列表
    :return: None
    """
    if not safe_updates and not skipped_updates:
        print("所有 skills 已是最新版本")
        return

    if safe_updates:
        print("可以自动更新的 skills:")
        for item in safe_updates:
            local_version = item["local_version"] or "未安装"
            print(f"- {item['slug']}: {local_version} -> {item['remote_version']}")

    if skipped_updates:
        print("因本地修改而跳过的 skills:")
        for item in skipped_updates:
            print(f"- {item['slug']}: {', '.join(item['modified_files'])}")


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数
    :return: 命令行参数
    """
    parser = argparse.ArgumentParser(description="Install lock and update SoMark skills")
    parser.add_argument(
        "--install-dir",
        type=Path,
        required=True,
        help="skills 安装目录，例如 ~/.agents/skills 或 ./.agents/skills",
    )
    parser.add_argument(
        "--init-lock",
        action="store_true",
        help="初始化 lock 文件",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="更新/安装 manifest 中所有 skills；默认只更新已安装 skills",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    install_dir = args.install_dir.expanduser().resolve()

    if args.init_lock:
        install_dir.mkdir(parents=True, exist_ok=True)
        lock = generate_lock(install_dir)
        write_lock(install_dir, lock)
        print(f"lock 已生成: {install_dir / LOCK_FILENAME}")
        return

    if not install_dir.exists():
        raise FileNotFoundError(f"安装目录不存在: {install_dir}")

    lock = read_lock(install_dir)
    if lock is None:
        raise RuntimeError(
            f"未找到 lock 文件: {install_dir / LOCK_FILENAME}\n"
            "请先运行: npx somark-skills init --install-dir <skills目录>"
        )

    manifest = download_manifest()
    updates = find_updates(
        lock=lock,
        manifest=manifest,
        include_not_installed=args.all,
    )

    safe_updates, skipped_updates = classify_updates_by_local_changes(
        install_dir=install_dir,
        lock=lock,
        updates=updates,
    )
    print_update_plan(safe_updates, skipped_updates)

    verified_updates = verify_safe_updates(
        manifest=manifest,
        safe_updates=safe_updates,
    )

    for slug, files in verified_updates.items():
        print(f"{slug}: 已校验 {len(files)} 个文件")

    if verified_updates:
        apply_verified_updates(
            install_dir=install_dir,
            lock=lock,
            verified_updates=verified_updates,
        )

        new_lock = generate_lock(install_dir)
        write_lock(install_dir, new_lock)
        print(f"lock 已更新: {install_dir / LOCK_FILENAME}")


if __name__ == "__main__":
    main()
