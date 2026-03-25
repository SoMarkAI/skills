import argparse
import asyncio
import difflib
import json
import os
import time
from pathlib import Path

import aiohttp

SOMARK_BASE = "https://somark.tech/api/v1"
ASYNC_URL = f"{SOMARK_BASE}/extract/async"
CHECK_URL = f"{SOMARK_BASE}/extract/async_check"

SUPPORTED_FORMATS = {
    ".pdf",
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp", ".heic", ".heif", ".gif",
    ".doc", ".docx", ".ppt", ".pptx",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SoMark 文档对比工具：解析两份文档并生成差异报告")
    parser.add_argument("-f1", "--file1", required=True, type=str, help="第一份文档路径（原始版本）")
    parser.add_argument("-f2", "--file2", required=True, type=str, help="第二份文档路径（新版本）")
    parser.add_argument("-o", "--output", type=str, default="./document_diff_output", help="输出目录（默认：./document_diff_output）")
    return parser.parse_args()


def resolve_file(path_str: str) -> Path:
    path = Path(path_str).resolve()
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")
    if not path.is_file():
        raise ValueError(f"路径不是文件: {path}")
    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValueError(f"不支持的文件格式: {path.suffix}")
    return path


async def submit_task(session: aiohttp.ClientSession, file_path: Path, api_key: str) -> str:
    data = aiohttp.FormData()
    data.add_field("output_formats", "markdown")
    data.add_field("output_formats", "json")
    data.add_field("api_key", api_key)
    data.add_field("file", file_path.read_bytes(), filename=file_path.name)

    async with session.post(ASYNC_URL, data=data) as resp:
        if resp.status != 200:
            error_text = await resp.text()
            raise RuntimeError(f"提交任务失败 [{resp.status}]: {error_text}")
        body = await resp.json()

    task_id = (body.get("data") or {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"响应中缺少 task_id: {body}")
    return task_id


async def poll_task(session: aiohttp.ClientSession, task_id: str, api_key: str,
                    max_retries: int = 300, interval: int = 2) -> dict:
    for _ in range(max_retries):
        await asyncio.sleep(interval)
        async with session.post(CHECK_URL, data={"api_key": api_key, "task_id": task_id}) as resp:
            if resp.status != 200:
                continue
            body = await resp.json()

        data = (body.get("data") or {})
        status = data.get("status")
        if status == "FAILED":
            raise RuntimeError(f"SoMark 任务失败: {data}")
        if status == "SUCCESS":
            result = data.get("result") or {}
            return result.get("outputs") or result

    raise RuntimeError(f"任务轮询超时: task_id={task_id}")


async def parse_document(session: aiohttp.ClientSession, file_path: Path, api_key: str) -> dict:
    print(f"  提交解析: {file_path.name}")
    task_id = await submit_task(session, file_path, api_key)
    print(f"  等待结果 (task_id={task_id})...")
    outputs = await poll_task(session, task_id, api_key)
    print(f"  解析完成: {file_path.name}")
    return outputs


def extract_markdown(outputs: dict, file_path: Path) -> str:
    md = outputs.get("markdown")
    if isinstance(md, str) and md.strip():
        return md
    # 降级：从 json outputs 中提取纯文本
    json_data = outputs.get("json")
    if isinstance(json_data, dict):
        lines = []
        for page in (json_data.get("pages") or []):
            for block in (page.get("blocks") or []):
                content = block.get("content", "").strip()
                if content:
                    lines.append(content)
        return "\n".join(lines)
    return ""


def build_diff_report(file1: Path, file2: Path, md1: str, md2: str) -> str:
    lines1 = md1.splitlines(keepends=True)
    lines2 = md2.splitlines(keepends=True)

    diff = list(difflib.unified_diff(
        lines1, lines2,
        fromfile=file1.name,
        tofile=file2.name,
        lineterm="",
    ))

    added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    unchanged = len([l for l in difflib.ndiff(lines1, lines2) if l.startswith("  ")])

    report_lines = [
        "# 文档对比报告",
        "",
        "## 概览",
        "",
        f"| 项目 | 内容 |",
        f"|------|------|",
        f"| 原始文件 | `{file1.name}` |",
        f"| 新版本文件 | `{file2.name}` |",
        f"| 新增行数 | {added} |",
        f"| 删除行数 | {removed} |",
        f"| 未变更行数 | {unchanged} |",
        "",
        "## 差异详情",
        "",
        "```diff",
    ]
    report_lines.extend(l.rstrip("\n") for l in diff)
    report_lines.append("```")
    report_lines.append("")

    return "\n".join(report_lines)


async def main() -> None:
    args = parse_args()
    api_key = os.environ.get("SOMARK_API_KEY", "")
    if not api_key:
        print("错误：请设置环境变量 SOMARK_API_KEY")
        raise SystemExit(1)

    file1 = resolve_file(args.file1)
    file2 = resolve_file(args.file2)

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n开始解析文档对...")
    start = time.time()

    async with aiohttp.ClientSession() as session:
        outputs1, outputs2 = await asyncio.gather(
            parse_document(session, file1, api_key),
            parse_document(session, file2, api_key),
        )

    md1 = extract_markdown(outputs1, file1)
    md2 = extract_markdown(outputs2, file2)

    if not md1:
        print(f"警告：{file1.name} 解析内容为空")
    if not md2:
        print(f"警告：{file2.name} 解析内容为空")

    # 保存各自的 markdown
    (output_dir / f"{file1.stem}.md").write_text(md1, encoding="utf-8")
    (output_dir / f"{file2.stem}.md").write_text(md2, encoding="utf-8")

    # 生成差异报告
    report = build_diff_report(file1, file2, md1, md2)
    report_path = output_dir / "diff_report.md"
    report_path.write_text(report, encoding="utf-8")

    # 保存摘要 JSON
    summary = {
        "file1": str(file1),
        "file2": str(file2),
        "output_dir": str(output_dir),
        "report": str(report_path),
        "file1_markdown": str(output_dir / f"{file1.stem}.md"),
        "file2_markdown": str(output_dir / f"{file2.stem}.md"),
        "elapsed_seconds": round(time.time() - start, 2),
    }
    (output_dir / "diff_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n完成：耗时 {summary['elapsed_seconds']} 秒")
    print(f"差异报告：{report_path}")


if __name__ == "__main__":
    asyncio.run(main())
