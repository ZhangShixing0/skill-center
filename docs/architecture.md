# 结构与维护

浏览器界面访问本机 Python HTTP 服务；服务读取配置范围内的 SKILL.md，在 SQLite 中保存库存、来源、已观察版本和可选使用记录。任务准备与草稿在浏览器处理，只有用户明确操作管理功能时才请求写入接口。

| 位置 | 职责 |
| --- | --- |
| `assets/dashboard/` | 页面与原生 JavaScript/CSS 源码 |
| `scripts/skill_store.py` | 来源扫描、库存、SQLite 与元数据 |
| `scripts/serve_dashboard.py` | loopback HTTP API 与页面服务 |
| `scripts/skill_center.py` | 启停、状态和诊断 |
| `scripts/demo.py` | 隔离示例环境，不读取个人安装库 |
| `assets/catalog/` | 通用显示元数据及工作流模板 |
| `examples/skills/` | 三个可选的原始示例 Skill |
| `SKILL.md` | 供 Agent 读取的管理说明 |

服务首次启动扫描默认 Codex 和兼容 Agents 目录；后续启动核对已索引项是否仍存在，完整扫描由用户触发。项目级路径在扫描来源中添加；初始配置没有预置个人项目。

原始 Skill 文件和内容版本应由用户自己的版本控制管理。当前应用可以记录已观察的版本和部分差异，但不提供面向所有第三方 Skill 的自动更新与回退系统。

修改源码后重启服务会重新安装页面文件。更新前备份自己的运行目录，关闭旧进程再启动新版本；不要用别人的运行数据库覆盖自己的记录。配置与数据结构的改变需要先提供迁移测试。
