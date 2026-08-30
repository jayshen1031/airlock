# Airlock MemHub 项目治理

- 文档状态：current
- 项目：airlock
- 安全域：personal
- Jira 工作项：VITA-12
- GitHub 跟踪项：#29

## 初始化完成标准

Airlock 的 MemHub 初始化只有在以下项目均通过时才算完成：

1. `configs/memhub.yaml`、机器访问策略和 `.memhub/agents/*.json` 使用相同的项目与安全域。
2. 项目已在中央 ProjectStore 注册并有 active Phase。
3. `.memhub/knowledge.yaml` 覆盖仓库拥有的持久知识，版本与中央 KnowledgeItem 一致。
4. `configs/knowledge-publication.json` 明确列出可发布文档、知识身份和目标路径。
5. Jira 和 GitHub 跟踪对象已经建立，初始化证据与遗留项可追踪。
6. 允许发布的知识已进入 `jay-knowledge-base`，私有站点构建和部署均有成功证据。
7. “提交记忆”规则包含 Jira、治理知识发布、OSS L0 收集，以及对
   `ingress → distill → consumer/ingest` 各阶段的独立验证。

## 本次缺口的原因

Airlock 于 2026-08-28 初始化；`.memhub/knowledge.yaml` 的 bootstrap 能力于
2026-08-29 才进入 Nexus Decision，因此旧项目没有自动回填。除此之外，原初始化器把
“生成项目骨架”当作成功条件，并未把 Jira、知识发布 allowlist、私有投影和部署回执作为
同一个 post-init 验收门禁，所以初始化命令成功不能证明治理闭环完成。

## 防止再次发生

- 初始化器和项目规范必须使用同一版本发布，禁止用旧 `src/bin/memhub` 入口验证新 CLI。
- 初始化结束后运行幂等 post-init audit；缺少任何上述工件时返回非零状态。
- bootstrap schema 升级时提供对已注册项目的 reconcile/migrate 操作，而不是只影响新项目。
- CI 校验 `.memhub/knowledge.yaml`、publication manifest、项目/安全域及 Jira 绑定的一致性。
- 私有知识部署只有在 source commit、知识库 projection commit 和部署 URL 都记录后才算完成。
