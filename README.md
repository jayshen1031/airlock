# Airlock

在现有 AI coding runtime 中，让另一个 Agent 独立审核代码；需要时，再进行有轮数上限的修复。
任务、Git 改动和审核结果通过本地文件交接，不传递聊天历史。

## 开始使用

需要 Python 3.11+、Git，以及已安装并登录、可在 runtime 的终端中调用的审核 CLI（`claude` 或 `codex`）。
当前 AI runtime 需要能读取本地文件并执行终端命令。

**1. 把 Airlock clone 到项目旁边，首次安装命令。**

```bash
# 在 your-project 的上一级目录执行
git clone https://github.com/jayshen1031/airlock.git
pipx install --editable ./airlock
airlock --help
```

目录结构：

```text
workspace/
├── your-project/    # 要审核的 Git 仓库
└── airlock/         # Airlock 工具
```

若没有 `pipx`，或需使用虚拟环境，见[安装说明](docs/usage.md#installation)。
同级目录便于 runtime 找到工具，也可以放在其他位置并提供实际路径。

**2. 在目标项目的 AI runtime 中说：**

> 用 Airlock 审核当前未提交的改动。工具在 `../airlock`，先读它的 README，
> 再调用 `airlock review`，让 Claude 独立审核；按报告汇总合理、不合理和建议。

也可以将 Claude 换成 Codex；通常选择与当前写代码的 Agent 不同的审核方。
首次说明路径后，后续可以直接说「用 Airlock 审核」。

若希望同时修复，请明确授权：

> 用 Airlock 审核并修复当前改动，Codex 修改、Claude 审核，最多修复三轮。

## Runtime 执行约定

- 在**目标项目**中执行 Airlock；也可以用 `--cwd /path/to/your-project` 指定仓库。
  默认审核已暂存、未暂存和未跟踪的当前改动，不是整库审计或已提交历史审核。
- 自然语言请求由当前 runtime 转成 CLI 调用，不会因 clone 而自动注册 skill 或集成。
  必须实际执行审核，再读取报告；仅给出口头意见不算 Airlock 审核。
- 审核方只读；仅授权审核时，不得自动启动修复。
  修复有轮数上限，只剩低风险问题时停下来交给用户决定。
- `BLOCKED`、超时、无效输出、执行失败或检测到审核方写入，都不能算通过。
  要求双方互审时，应分别执行两次审核；只有两方都成功执行才算完成。
- Airlock 不自动 commit、push、merge、reset 或扩大 provider 权限。

审核报告保存在目标项目的 `.airlock/runs/<run-id>/review.md`；修复汇总为 `review-report.md`。
这些本地审计文件不应提交到 Git。测试门禁、退出码、更新和排障见[详细用法](docs/usage.md)。

## 更多

- [产品需求](docs/product-requirements_CN.md) · [架构](docs/architecture_CN.md)
- [知识与运行时边界](docs/adr/0001-knowledge-and-runtime-boundaries.md)：独立运行无需 MemHub/Nexus。

Airlock 是独立开源项目，与 Anthropic、OpenAI、Google 等厂商无官方关联。
Provider CLI 需自行安装、配置并遵守其许可与服务条款；相关商标归各自所有者。

采用 [Apache License 2.0](LICENSE)，项目归属见 [NOTICE](NOTICE)。
