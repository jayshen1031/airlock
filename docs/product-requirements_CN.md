# Airlock v0.1 产品需求

## 1. 产品定位

Airlock 是一个面向 AI coding runtime 的 **Cross-Agent Review Execution Layer**：用户可在
Codex、Claude 等当前 runtime 中用自然语言要求“用 Airlock 审查或修复”，runtime 再调用
Airlock 的稳定 CLI 协议，让一个 coding agent 负责实现、另一个 agent 对 Git diff 做独立、
只读、结构化审核，并将 findings 自动交回 writer 进行有限次数的修复与复审。

一句话价值主张：

> Keep the terminals. Remove the copy-paste.

它不替代 Codex、Claude Code、iTerm2 或其他现有交互界面，也不提供新的聊天界面。用户
通常停留在当前 AI coding runtime 中，以自然语言触发 Airlock；CLI 是 runtime 背后的
可移植、可审计执行协议，也保留给 CI、脚本和希望直接操作终端的用户。

Airlock 核心与 terminal emulator 无关，支持 iTerm2、Terminal.app、Warp、WezTerm、
tmux、VS Code terminal 和 CI。v0.1 不识别、附着或模拟操作用户已经打开的 pane；每次
agent 执行由 Airlock 通过官方 CLI 的非交互模式启动，并用 repository root、run ID 和
role 标识。terminal-specific pane launcher 只能作为未来可选集成，不能进入核心流程。

## 2. 目标用户与现有痛点

目标用户同时使用两个以上 coding agent，典型流程是：

1. 在 Codex 或 Claude 中描述任务，并要求当前 runtime 使用 Airlock。
2. 当前 runtime 将原始任务映射为显式的 review 或 repair 调用。
3. Airlock 将 Git diff、测试证据和结构化协议交给独立 reviewer。
4. Airlock 将 findings 交回 writer，并按边界复审。
5. 当前 runtime 读取可读报告，向用户汇报每轮合理、不合理和建议。
6. 用户判断问题是否足够收敛并结束任务。

主要痛点是重复复制粘贴、交接格式不稳定、审核轮次不可追踪，以及 reviewer 可能被
writer 的完整对话锚定。

## 3. v0.1 目标

- 支持 Claude Code 和 Codex CLI。
- 支持 `writer` 与 `reviewer` 两个角色。
- 以当前 Git workspace 作为共享事实来源。
- 运行用户配置的测试命令并保存结果。
- reviewer 只能读取仓库，不得修改工作区。
- reviewer 输出 `approve`、`reject` 或 `blocked`。
- `reject` 必须产生机器可读的 structured findings。
- 支持 findings 驱动的 repair loop。
- 支持最大轮次、超时和基础 stuck detection。
- 所有状态和 artifact 保留在本地，可被人查看和接管。
- AI runtime 能以自然语言请求稳定映射到显式 CLI 调用，并读取可读报告回传。
- 只有被请求的独立 reviewer 都真实执行成功，才能声称互审完成。
- `blocked`、provider failure、timeout 或 malformed verdict 必须报告为工具失败，不得包装成
  审查意见或批准。

## 4. 非目标

v0.1 不提供：

- Web UI；
- 读取或操纵既有 iTerm2/tmux pane；
- 通用 multi-agent chat；
- 十个以上 provider；
- MCP 或 ACP transport；
- 长期向量记忆、Neo4j 或 agent conversation copy；
- 项目管理、任务分配或自治团队；
- 自动 merge、自动 push 或绕过人工权限；
- 替用户决定业务需求是否正确。

## 5. Runtime 调用契约与核心命令

自然语言是用户交互层，CLI 是执行层。当前 runtime 必须保留用户原始任务与授权边界，选择
显式的 writer/reviewer，调用以下命令，并读取 `.airlock/runs/<run-id>/review.md` 或
`review-report.md` 汇报结果。runtime 不得因用户只要求 review 而自行升级为 repair，也不得
把当前会话历史作为独立 reviewer 的隐藏输入。

### `airlock review`

对当前 Git diff 进行一次独立审核。它是 v0.1 的第一个交付功能，也是最低风险的
dogfood 入口。

预期行为：

1. 验证当前目录是 Git repository。
2. 捕获 base ref、working-tree diff 和必要的状态元数据。
3. 可选运行 test command。
4. 以只读模式调用 reviewer。
5. 校验 reviewer JSON。
6. 将结果写入 `.airlock/runs/<run-id>/review.json`。
7. `approve` 返回退出码 0，`reject` 或 `blocked` 返回非零退出码。

### `airlock repair`

先对当前 workspace 执行审核，仅将 structured findings 交给 writer 修复；随后重新运行
test gate 和独立审核。命令由用户显式触发，受 `max_iterations`、timeout、重复 findings、
无 diff 进展和重复 workspace state 约束，不自动 commit、push、merge 或 reset。

### `airlock run`

执行有边界的 `implement -> test -> review -> repair -> review` 流程。达到
`max_iterations`、重复 findings、无 diff 进展、超时或 blocked 时必须停止并把控制权
交还用户。

## 6. 配置

仓库根目录可包含：

```yaml
writer:
  provider: codex

reviewer:
  provider: claude

gates:
  test_command: pytest -q

loop:
  max_iterations: 3
```

环境变量只承载运行时覆盖或敏感配置；仓库配置不得包含凭据。

## 7. 审核协议

reviewer 必须输出：

```json
{
  "verdict": "reject",
  "summary": "存在一个高风险回归",
  "findings": [
    {
      "severity": "high",
      "file": "src/foo.py",
      "line": 123,
      "issue": "异常路径没有恢复状态",
      "suggestion": "在返回前恢复状态并增加回归测试"
    }
  ]
}
```

约束：

- verdict 为 `approve | reject | blocked`；
- `reject` 至少包含一个 finding；
- `approve` 不得包含未解决的 blocking finding；
- severity 为 `critical | high | medium | low`；
- file 和 line 允许在无法精确定位时为空，但 issue 必须可执行；
- schema 校验失败视为 provider failure，不得默认为 approve。
- Provider 仅可对连接中断和 HTTP 429、502、503 最多重试两次；每次尝试必须单独审计，
  且重试前 HEAD、diff hash、workspace fingerprint 必须保持不变。认证、权限、schema、
  timeout、reviewer mutation 和未知错误不得重试，最终失败必须为 `blocked`。

## 8. 验收标准

v0.1 可发布需要满足：

- 能在一个临时 Git repo 中完成 Codex/Claude 双向组合的 review-only 流程；
- reviewer 的写入尝试不会改变工作区；
- malformed JSON、CLI 不可用、超时和非零退出都有清晰错误；
- 同一个 run 的 task、diff 摘要、测试结果、review 和迭代状态可审计；
- repair loop 不超过配置上限；
- 单元测试不依赖真实 provider，真实 CLI 验证作为显式 integration tests；
- 文档能让新用户在 10 分钟内完成首次 review。
- 用户能在 Codex 或 Claude 中仅用自然语言触发一次 Airlock review，并获得 artifact 路径与
  可读结果。
- 任一指定 reviewer 未执行、超时或 blocked 时，系统不会声称互审已经完成。

## 9. 后续候选能力

- `airlock watch`：保持 terminal-first 的显式监听模式；
- resume/cancel；
- 多 reviewer 或 adversarial review；
- Gemini 等额外 adapter；
- CI review gate；
- 可选 MemHub knowledge integration，但核心 runtime 不依赖 MemHub。
