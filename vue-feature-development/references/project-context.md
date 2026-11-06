# inspect-frontend 功能定位

仅在 inspect-frontend 项目开发时读取。下列路径相对目标项目根目录，本技能仓库不包含这些业务文件。先读目标项目的 `AGENTS.md`，主应用再读 `frontend/AGENTS.md` 与 `frontend/README.md`。本文件提供检索起点，规则、版本和命令由这些拥有者维护；其他三个应用按根指令进入各自工程。

| 本次需要决定的能力 | 检索与阅读起点 |
| --- | --- |
| 组件、全局方法与导入 | `frontend/src/main.js`、`frontend/vite/plugins/auto-import.js`；再找组件的实际调用者 |
| 查询、分页、字典和导出 | `frontend/src/views/system/role/index.vue`、`frontend/src/api/system/role.js`，再与当前领域相邻页面比较 |
| 请求、企业范围和响应 | `frontend/src/api/` 对应模块、`frontend/src/utils/request.js`、`frontend/src/utils/tenantScope.js` 及调用者 |
| 菜单、权限和返回 | `frontend/src/permission.js`、`frontend/src/router/index.js`、`frontend/src/store/modules/permission.js`；查 `v-hasPermi` 的实际使用 |
| 模型、卡片和测点 | `frontend/src/layout/components/Navbar.vue` → 所属 `frontend/src/views/dataCenter/` 宿主 → 型号组件；查看 `realTime.vue`、`dongMingLanTian.vue` 及 `frontend/src/components/Line/`、`frontend/src/utils/modelCache.js`、`frontend/src/utils/dracoLoaderManager.js` 的契约与消费者 |
| 检查与交付 | `frontend/README.md` 的“检查与维护”，再核对所属应用的 `package.json` |

这些页面和工具是查找候选，不是可整份复制的模板。共享查看器与特定型号组件的职责可能不同；确认 props/events 和状态/资源所有权后再决定复用范围。不要把单设备的展示约定推广到列表、其他型号或其他应用。

需要审查实现时，按当前审查任务使用已有前端审查流程；需要复现异常时进入故障调查。当前开发任务仍由本 Skill 完成，不因可能涉及审查或测试就自动串行加载所有 Skills。
