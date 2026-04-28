#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

function run(command, args) {
  const result = spawnSync(command, args, {
    stdio: "inherit",
    shell: false,
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function pythonCommand() {
  const candidates = ["python3", "python"];

  for (const candidate of candidates) {
    const result = spawnSync(candidate, ["--version"], {
      stdio: "ignore",
      shell: false,
    });

    if (result.status === 0) {
      return candidate;
    }
  }

  console.error("未找到 Python，请先安装 python3。");
  process.exit(1);
}

function updaterPath() {
  return path.resolve(__dirname, "..", "scripts", "somark_skills_update.py");
}

function parseOptions(args) {
  const options = {
    installDir: null,
    all: false,
  };

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];

    if (arg === "--install-dir") {
      const value = args[i + 1];
      if (!value) {
        console.error("--install-dir 需要一个目录路径。");
        process.exit(1);
      }
      options.installDir = value;
      i += 1;
      continue;
    }

    if (arg === "--all") {
      options.all = true;
      continue;
    }

    console.error(`未知参数: ${arg}`);
    process.exit(1);
  }

  return options;
}

function updaterArgs(options) {
  const args = [updaterPath()];

  if (options.installDir) {
    args.push("--install-dir", options.installDir);
  }

  return args;
}

function init(options) {
  if (!options.installDir) {
    console.error("init 需要 --install-dir <dir>。");
    process.exit(1);
  }
  if (options.all) {
    console.error("init 不支持 --all。");
    process.exit(1);
  }

  const python = pythonCommand();
  run(python, [...updaterArgs(options), "--init-lock"]);

  console.log("SoMark skills lock 初始化完成。");
}

function update(options) {
  if (!options.installDir) {
    console.error("update 需要 --install-dir <dir>。");
    process.exit(1);
  }

  const python = pythonCommand();
  const args = updaterArgs(options);

  if (options.all) {
    args.push("--all");
  }

  run(python, args);

  console.log("SoMark skills 更新完成。");
}

function main() {
  const command = process.argv[2];

  if (command === "init") {
    init(parseOptions(process.argv.slice(3)));
    return;
  }

  if (command === "update") {
    update(parseOptions(process.argv.slice(3)));
    return;
  }

  console.log(`Usage:
  somark-skills init --install-dir <dir>
  somark-skills update --install-dir <dir>
  somark-skills update --all --install-dir <dir>

安装请使用：
  npx skills add https://github.com/SoMarkAI/skills

如果你把 SoMark skills 安装到了多个目录，请分别对每个目录执行 init 和 update。`);
  process.exit(1);
}

main();
