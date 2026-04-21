# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

## Project Overview

SoMark Skills — a collection of AI agent skills for document parsing and image OCR, powered by the [SoMark](https://somark.ai) API. Skills are installable via `npx skills add https://github.com/SoMarkAI/skills` and work with Codex, Cursor, Cline, and other agents.

## Repository Structure

```
skills/
  image-parser/                    # OCR skill: extracts text + bounding-box coordinates from images
  somark-document-parser/          # Document parsing skill: PDF/Word/PPT/images → Markdown/JSON
  document-diff/                   # Compare two documents, generate structured diff report
  contract-reviewer/               # Contract risk review with severity ratings
  resume-parser/                   # Resume → structured JSON + candidate assessment
  tender-analyzer/                 # Extract requirements, scoring criteria, checklists from RFPs
  paper-digest/                    # Academic paper → structured research card
  financial-report-analyzer/       # Annual report → financial metrics, risk signals, management commentary
  pitch-screener/                  # VC/angel pre-meeting investment memo (deck parse + web background research)
```

Each skill has three files: `SKILL.md` (frontmatter with name/description/metadata + usage instructions), `_meta.json` (slug + version), and a Python script.

## Key Architecture Differences Between Skills

- **image-parser** uses the **sync** SoMark endpoint (`/parse/sync`) and stdlib-only (`urllib`). No external dependencies.
- All other skills use the **async** SoMark endpoint (`/parse/async` + `/parse/async_check` polling) and require `aiohttp`.
- **pitch-screener** additionally uses web search (via available MCP tools) for background research after parsing.

## Running the Scripts

```bash
# Contract reviewer (single file)
python skills/contract-reviewer/contract_reviewer.py -f <contract_file> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Document diff (two files)
python skills/document-diff/document_diff.py -f1 <original_file> -f2 <new_file> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Financial report analyzer (single file)
python skills/financial-report-analyzer/financial_report_analyzer.py -f <report_file> -o <output_dir> --output-formats '["markdown", "json", "somarkdown"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Image parser (single file)
python skills/image-parser/image_parser.py -f <image_path> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Image parser (directory)
python skills/image-parser/image_parser.py -d <image_dir> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Paper digest (single file)
python skills/paper-digest/paper_digest.py -f <paper_file> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Pitch screener (single file)
python skills/pitch-screener/pitch_screener.py -f <pitch_file> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Resume parser (single file)
python skills/resume-parser/resume_parser.py -f <resume_file> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# SoMark document parser (single file)
python skills/somark-document-parser/somark_parser.py -f <file_path> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# SoMark document parser (directory)
python skills/somark-document-parser/somark_parser.py -d <dir_path> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'

# Tender analyzer (single file)
python skills/tender-analyzer/tender_analyzer.py -f <tender_file> -o <output_dir> --output-formats '["markdown", "json"]' --element-formats '{"image": "url", "formula": "latex", "table": "html", "cs": "image"}' --feature-config '{"enable_text_cross_page": false, "enable_table_cross_page": false, "enable_title_level_recognition": false, "enable_inline_image": true, "enable_table_image": true, "enable_image_understanding": true, "keep_header_footer": false}'
```

Both scripts require the `SOMARK_API_KEY` environment variable.

## Conventions

- SKILL.md frontmatter uses the `metadata.openclaw` schema: emoji, `requires.env`, and `primaryEnv`.
- Error messages and CLI output in the Python scripts are in Chinese.
- The skill name in SKILL.md frontmatter must match the directory name (e.g., `name: image-parser` for `skills/image-parser/`).
