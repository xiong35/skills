# 宿主与可移植边界

仅在选择安装位置、分发或排查加载问题时读取。优先遵循用户指定位置和目标项目约定，不从技能格式推断所有宿主的发现路径。

| 层次 | 可共享 | 需要独立核实 |
| --- | --- | --- |
| 内容 | SKILL.md 与必要资源，任务/输入/输出/验证流程 | 资源可访问性、工具前提 |
| 指令 | 项目事实与契约可保持单一来源 | AGENTS/CLAUDE/规则的实际加载与作用域 |
| 调用 | 清楚的 name/description | 显式调用语法、隐式选择和重复名称行为 |
| 执行 | 参数化 CLI、相对路径、明确输出 | Windows/macOS、运行时版本、权限、网络、MCP |
| 扩展 | 必要时单独增加宿主 metadata | UI、插件、Hook、子 Agent、权限设置；不假定可直接移植 |

Codex 的仓库技能路径与 metadata 见 [官方 Skills](https://learn.chatgpt.com/docs/build-skills)。Claude 与 Cursor 分别查 [Claude Skills](https://code.claude.com/docs/en/skills)、[Cursor Skills](https://cursor.com/docs/skills)。这些链接是核对入口，不代表本次已完成目标版本验收。

不默认制作多个手工副本或要求 symlink。确需生成适配时，先实测单一发现路径、避免重复加载，并记录来源、所有权和过期检查。先确认需求，再制作适配脚本；不在通用工厂中更改私人配置或安装插件。
