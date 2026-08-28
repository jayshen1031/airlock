# Airlock v0.1 架构设计

## 1. 设计原则

Airlock 的 shared memory 是 Git workspace，不是两个 agent 的聊天记录。

```text
                    Git repository
          code / diff / tests / run artifacts
                         |
              +----------+----------+
              |                     |
              v                     v
        writer (write)        reviewer (read-only)
```

writer 只接收任务、当前仓库和结构化 findings；reviewer 只接收任务约束、diff、测试结果
以及审核协议。默认不把 writer 的推理或 conversation history 交给 reviewer，以保留审核
独立性。

## 2. Terminal 与多 pane 模型

Airlock 不把 iTerm2 pane 当作 agent transport。核心 runtime 通过 provider CLI 的
非交互入口创建受控子进程，因此不需要读取窗口标题、屏幕文本或模拟键盘输入。

```text
iTerm2 / tmux / Warp / CI
          |
          v
      airlock CLI
          |
          +-- run-id A / writer subprocess
          `-- run-id A / reviewer subprocess
```

执行身份由 `repository root + run-id + role` 决定，与 pane 数量无关。用户可以在任意
数量的 pane 中运行 `airlock status` 或查看 artifact，但同一 run 的状态转换由 run store
锁保护。v0.1 不附着到已经存在的 Claude/Codex conversation；未来的 iTerm2/tmux
integration 只负责打开 pane、显示状态或 tail event stream，不参与 orchestration。

## 3. 组件边界

```text
CLI
 |
 v
Application service / loop controller
 |-- Git workspace adapter
 |-- Test gate
 |-- Agent adapter registry
 |     |-- Codex adapter
 |     `-- Claude adapter
 |-- Review schema validator
 `-- Local run store
```

### CLI

解析 `review`、`repair`、`run` 命令和用户覆盖项，只负责展示与退出码，不承载 provider
逻辑。

### Loop controller

实现显式状态机：

```text
CREATED
  -> IMPLEMENTING
  -> TESTING
  -> REVIEWING
     -> APPROVED
     -> REJECTED -> REPAIRING -> TESTING
     -> BLOCKED
  -> EXHAUSTED
  -> FAILED
```

所有转换写入 run store。任何异常不得隐式转换为 APPROVED。

### Agent adapter

最小接口：

```python
class AgentAdapter(Protocol):
    def available(self) -> bool: ...
    def run(self, request: AgentRequest) -> AgentResult: ...
```

`AgentRequest` 至少包含 prompt、cwd、`read | write` mode、timeout 和期望的输出格式。
Provider-specific flags、权限映射和输出解析封装在 adapter 内，不泄漏到 controller。

v0.1 直接使用 subprocess 调已安装的官方 CLI。暂不引入 ACP、daemon 或 provider SDK。

### Git workspace adapter

负责：

- 解析 repository root；
- 捕获 HEAD/base ref、tracked/untracked 状态和 diff；
- 在每轮前后计算变化摘要；
- 检测 reviewer 是否产生工作区写入；
- 生成 stuck detection 所需的稳定 fingerprint。

Airlock 不自动 commit、push、merge、reset 或清理用户工作区。

### Test gate

运行用户声明的单一命令，记录 command、cwd、exit code、duration 和截断后的 stdout/
stderr。测试失败默认进入 repair；若没有 writer 或 repair 未授权，则停止并报告。

### Local run store

```text
.airlock/
  config.yaml
  runs/
    <run-id>/
      task.md
      state.json
      diff.patch
      test-result.json
      review.json
      events.jsonl
```

`.airlock/runs/` 默认应被 Git 忽略；示例配置可提交。run artifact 使用原子写入，避免
进程中断后出现半写状态。

## 4. 只读 reviewer

只读不是 prompt 中的一句话，而是需要分层保证：

1. 使用 provider CLI 提供的最低权限模式；
2. prompt 明确禁止写入和命令副作用；
3. 调用前后比较 Git/worktree fingerprint；
4. 检测到写入时将 run 标记为 failed，并报告变化，不自动删除或 reset；
5. 后续可加入 OS sandbox，但不作为首个跨平台版本的前置条件。

仅靠 Git diff 无法发现所有 ignored-file 写入，因此 v0.1 文档必须陈述该限制。

## 5. Stuck detection

满足任一条件时停止自动循环：

- 达到 `max_iterations`；
- 连续两轮 repository diff fingerprint 相同；
- 连续两轮 normalized findings fingerprint 相同且 writer 没有有效进展；
- writer 或 reviewer 报 blocked；
- provider timeout、cancel 或无法解析输出；
- test command 配置无效。

停止意味着保存证据并把控制权交还用户，不意味着丢弃已有修改。

## 6. 安全与权限

- 默认只在用户明确调用命令后启动 agent；
- reviewer 永远请求 read mode；
- writer 只在 `repair`/`run` 或用户显式授权时请求 write mode；
- 不读取或传输凭据；
- 不自动扩大 CLI 权限；
- 不执行不可恢复的 Git 操作；
- 所有 provider invocation、退出码和状态转换可审计；
- 最终通过标准仍由用户和项目既有 quality gates 决定。

## 7. Python package layout

```text
src/airlock/
  cli.py
  config.py
  models.py
  loop.py
  git_workspace.py
  test_gate.py
  run_store.py
  adapters/
    base.py
    claude.py
    codex.py
tests/
  unit/
  integration/
```

建议使用 Python 3.11+、标准库 subprocess、PyYAML 和 schema/model validation 库。
依赖保持极小，adapter integration tests 默认不运行真实 provider。

## 8. 实施顺序

1. 数据模型、review schema、run store。
2. Git workspace capture 与 reviewer write detection。
3. fake adapter 和 `airlock review` controller。
4. Codex/Claude adapters。
5. test gate 和 CLI UX。
6. repair loop、轮次限制和 stuck detection。
7. 真实 CLI smoke tests、打包和 CI。

这一顺序保证第一阶段就能 dogfood review-only 流程，并把复杂的 process lifecycle 延后
到已有真实使用反馈之后。
