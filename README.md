<div align="center">

<h1>Skill Center</h1>

<img src="docs/media/workbench.png" alt="Skill Center 松绿工作台，展示三个随项目提供的合成示例能力" width="1200">

<p><strong>把已安装的 Skills 整理成可查找、可理解、可开始使用的本地能力工作台。</strong></p>

<p><a href="#解决什么问题">解决的问题</a> · <a href="#先看演示">演示</a> · <a href="#快速开始">快速开始</a> · <a href="#能力与边界">能力与边界</a> · <a href="CONTRIBUTING.md">参与贡献</a></p>

<p><a href="CHANGELOG.md"><img src="docs/badges/stage.svg" alt="Stage Alpha"></a> <a href="requirements.txt"><img src="docs/badges/python.svg" alt="Python 3.10 or newer"></a> <a href="LICENSE"><img src="docs/badges/license.svg" alt="MIT License"></a></p>

</div>

> [!NOTE]
> 公开测试版 `0.1.0-alpha.1`。面向已经使用 Codex Skills、希望整理本地能力库的人。界面目前以中文为主；实际任务交给已有 Agent 执行。浏览器展示不代表已经运行 Skill。

## 解决什么问题

装了很多 Skills 后，困难常常变成：记不住有什么、不知道本次任务该选哪个、找到后也不清楚要准备哪些材料。

Skill Center 把能力库存、用途说明与任务准备放在一起。你可以浏览自己安装的能力，也可以描述任务，检查匹配依据，再准备交给 Codex 的执行说明。应用运行在本机，不需要模型 API Key。

## 先看演示

仓库包含三个原始示例：项目 README、网页体验检查、市场与竞品调研。它们用于演示和首次体验，不是从作者的私人能力库导出的内容。页面里显示的能力数量取决于你自己的安装；不会自动获得作者电脑上的 Skills。

```sh
python scripts/demo.py --open
```

演示在独立临时目录运行，只加载这三个示例，不扫描你的个人目录。默认地址是 `http://127.0.0.1:8767/my-skills.html`。终端保持打开，按 Ctrl+C 结束；演示服务和临时数据库随后清理。浏览器中的显式草稿仍由该浏览器保存，需在界面中清空。

![按任务选择能力：输入项目管理工具调研目标，查看匹配依据和材料建议](docs/media/task-finder.png)

上面及页首截图来自实际运行的隔离演示，全部条目为随仓库提供的示例。

## 从目标到开始使用

![流程：描述任务、选择能力、准备说明、交给已有 Agent 执行](docs/media/workflow.svg)

1. 点击“按任务找能力”，例如输入“调研项目管理工具市场与竞品”。
2. 核对候选的匹配理由、适用场景和材料建议。最多显示三项当前已发现的能力。
3. 点击“准备这个任务”，补充材料与交付要求。已有草稿会保留，新目标需要明确选择采用。
4. 复制执行说明到 Codex，按需要附上实际材料。网页不上传文件，也不自动开始执行。

## 快速开始

需要 **Python 3.10 或更新版本**，以及现代浏览器。运行依赖仅有 Python 标准库，`requirements.txt` 中没有需要安装的第三方包。当前在 Windows 完成本地验证；macOS/Linux 使用相同 Python 命令，但尚未完成实机验证。

```sh
git clone https://github.com/ZhangShixing0/skill-center.git
cd skill-center
python scripts/skill_center.py start --open
```

Windows 也可以双击 `open-skill-center.cmd`。macOS/Linux 上若命令名为 `python3`，将上面的 `python` 换为 `python3`。

启动后打开 `http://127.0.0.1:8765/my-skills.html`。首次启动扫描标准 Codex 和兼容 Agents 目录；项目级目录需在“扫描来源”中预览并添加。没有安装任何 Skill 时，可以先运行隔离演示，或安装自己的 Skills 后点击“刷新本地索引”。

```sh
python scripts/skill_center.py doctor
python scripts/skill_center.py status
python scripts/skill_center.py stop
```

端口被占用时使用 `python scripts/skill_center.py start --port 8875 --open`。启动器通过本机健康检查确认服务就绪；异常时运行 `doctor`，检查 Python、端口和运行目录。

默认数据保存在主目录下的 `Documents/Codex Skill Center`。可用 `SKILL_CENTER_HOME` 指定新的独立数据目录；扫描来源可在页面配置。不要把该运行目录提交到 GitHub。

<details>
<summary>同时作为 Skill 供 Codex 调用</summary>

仓库根目录的 `SKILL.md` 是管理入口，名称为 `skill-manager`。如希望 Codex 自动发现它，可将整个仓库克隆到尚不存在的个人 Skill 子目录；已有同名目录时先核对，不要覆盖。

```sh
git clone https://github.com/ZhangShixing0/skill-center.git ~/.codex/skills/skill-manager
```

让当前 Agent 会话重新加载能力后，用 `$skill-manager` 请求启动、诊断或扫描。安装此管理入口不会安装演示之外的第三方 Skills，也不保证所有 Agent 都采用同一发现机制。

</details>

## 能力与边界

| 能力 | 当前行为 |
| --- | --- |
| 能力库 | 搜索、分类、来源筛选、收藏与就地详情 |
| 按任务查找 | 本地用途规则与名称/描述匹配，提供依据；没有接入模型推理 |
| 任务准备 | 原文带入、可编辑执行说明、显式草稿、复制与 TXT 下载 |
| 来源与库存 | 预览扫描范围、区分来源与作者归属、重复位置和已移除记录 |
| 版本与回顾 | 已观察内容版本、部分差异、可选调用记录与反馈 |
| 工作流 | 作者建议的步骤组合及缺失项；不会自动编排执行 |

仅监听本机地址。没有云端账户、团队权限、模型推荐、跨工具自动同步或第三方 Skill 自动更新系统。调用统计是部分覆盖的“已记录使用”，零记录不能证明没有使用。复杂或陌生任务可能匹配不到，请改写目标或直接浏览能力库。

## 安全与数据

资料与代码是否适合执行，仍需要用户和 Agent 核对。来源标签不等同于安全审计。数据库与个人配置留在运行目录；草稿由用户明确保存到浏览器。分享诊断或截图前请检查其中的路径与内容。

详见 [安全与数据边界](SECURITY.md)、[结构与维护](docs/architecture.md) 和 [来源与许可](docs/third-party-notices.md)。

## 验证与反馈

后端自测、HTTP 边界、启停流程、任务匹配与浏览器操作均有可运行检查；命令见 [贡献说明](CONTRIBUTING.md)。可选浏览器开发依赖位于 `package.json`，不影响普通用户启动应用。

当前尚未启用 GitHub Actions。仓库保留了 [可选 CI 配置](docs/ci/verify.yml)，供维护者获得工作流发布权限后启用；本地测试通过不代表跨平台 CI 已通过。

欢迎反馈三件事：能否独立安装、能否找到适合任务的能力、能否顺利准备第一次执行说明。请提供系统与版本、复现步骤和经过检查的截图，避免上传真实数据库、令牌和个人路径。[提交问题](https://github.com/ZhangShixing0/skill-center/issues)。

后续优先根据试用反馈改善通用任务匹配、版本差异展示和首次使用体验。[变更记录](CHANGELOG.md) 描述当前源码版本，不承诺未实现的功能。

## 许可

本项目和随附的三个原始示例采用 [MIT License](LICENSE)。扫描到的第三方 Skills 仍遵守各自的许可，本项目不重新授权它们。
