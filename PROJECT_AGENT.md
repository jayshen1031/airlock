# airlock Project Agent Rules

## 1. Workspace Zones

| Zone | 目录 | 用途 |
|------|------|------|
| **SoT** | `src/`, `configs/`, `docs/`, `scripts/` | 正式代码、配置、文档 |
| **Artifacts** | `artifacts/` | 报告、快照、导出文件 |
| **Sandbox** | `.sandbox/` | 临时文件、日志、缓存 |
| **Capsules** | `capsules/YYYY-MM-DD/` | 会话胶囊 (MemHub distill 产出) |

## 2. Rules

- [safety] 不自动删除 SoT 文件, 清理前必须 snapshot
- [safety] 临时文件 → .sandbox/, 正式代码 → SoT 目录
- [safety] 双语文档: _CN.md + _EN.md
- [sot] SoT: src/, dbt/, devops/, configs/, docs/, scripts/
- `.sandbox/**` 不纳入知识索引
- 架构、部署和操作文档必须标记 `current/superseded/archived`；每个主题和语言只能有一个 current SoT
- 被替代文档移入 `docs/archive/` 并记录 `superseded_by`；`docs/archive/**` 不进入默认知识索引
- 至少每 30 天及每次发布前执行文档生命周期审计
- 公司、家庭等电脑属于不同 host scope；不得用一台电脑的 ignored 数据、符号链接解析、容器或进程状态推断另一台电脑
- 清理报告必须记录 `host_id` 和 `repo_commit`；跨主机差异标记为 `HOST_VARIANT`
