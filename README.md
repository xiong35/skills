# Skills

从 inspect-frontend 项目整理的 Agent Skills。每个目录包含独立的 `SKILL.md` 入口及其配套资源。

| Skill | 用途 |
| --- | --- |
| [bug-investigation](bug-investigation/SKILL.md) | 异常复现、调用链调查和根因验证 |
| [frontend-code-review](frontend-code-review/SKILL.md) | 有证据的前端代码审查 |
| [vue-feature-development](vue-feature-development/SKILL.md) | Vue 业务功能开发与既有能力复用 |
| [industrial-photo-modeling](industrial-photo-modeling/SKILL.md) | 工业设备照片建模、Blender/GLB 交付及项目接入 |
| [skill-authoring](skill-authoring/SKILL.md) | 可复用技能制作、检查和评估 |

## 使用

按需将完整技能目录复制到目标项目的 `.agents/skills/`，或所用工具支持的技能目录。保留 `references/`、`scripts/`、`assets/` 等配套文件，不能只复制 `SKILL.md`。不同宿主的发现与安装方式以其文档为准。

三个前端技能保留 inspect-frontend 的条件性项目导航；导航中的业务路径相对目标项目根目录。项目的 AGENTS、README 和业务源码不包含在本仓库中。在其他项目使用时，读取该项目自身约定，不套用示例项目的接口、目录或身份数据。

工业建模技能包含立环脉动除尘机的比例建模案例源码、参数与校验基准；生成 Blender 工程需要已有的 Blender 环境。案例不是其他设备的通用模型，也不代表实测尺寸。原始照片、业务 GLB 和私人配置未包含在本次同步中。

`evals/` 保存评估材料，不会自动调用模型。`skill-authoring/scripts/validate_skill.py` 使用 Python 3.9+ 标准库，可检查入口、命名和显式本地引用；结构检查通过不代表真实业务或宿主兼容性已验收。

原有的 `social-card-skill.md` 保持不变。
