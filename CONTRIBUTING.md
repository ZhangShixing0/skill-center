# 参与贡献

欢迎提交可复现的问题、通用任务示例、安装说明改进和修复。项目处于公开测试阶段；涉及自动安装、修改 Skill 或模型接口的变化，请先说明使用场景与数据边界。

运行环境为 Python 3.10+，应用不需要第三方 Python 包。可选的浏览器检查使用 Node.js 20+ 与 `package.json` 中锁定的 Playwright 开发依赖。

```sh
python scripts/self_test.py
python scripts/http_e2e.py
python scripts/lifecycle_test.py
npm ci
npx playwright install chromium
npm test
npm run test:browser
```

测试创建自己的临时数据；演示命令为 `python scripts/demo.py`。不要使用真实数据库制作测试或截图。提交前检查 `git diff --check`，只提交源码、通用配置和需要的测试。

GitHub Actions 尚未启用。[`docs/ci/verify.yml`](docs/ci/verify.yml) 是可选模板，计划在 Windows/Linux、Python 3.10/3.13 下检查后端，并在 Linux Chromium 下检查浏览器操作。维护者取得 GitHub 工作流写入权限后，可将它移动到 `.github/workflows/verify.yml` 并检查首次运行结果。模板的存在不表示这些环境已验证。

页面源文件在 `assets/dashboard/`；启动时复制到运行目录，不应修改运行目录来实现新功能。任务匹配位于 `assets/dashboard/assets/task-match.js`；必须有依据、只匹配当前条目，不把匹配分数显示为模型置信度。

提交 PR 时说明解决的问题、测试结果及对已有数据的影响。贡献代码沿用本项目 MIT 许可；第三方代码与素材需标明来源和适用许可。
