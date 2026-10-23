@AGENTS.md

# Claude Code 项目入口

本目录为「AI 智行助手」演示项目。项目结构、接口契约、运行方式、验证要求和 Git 工作范围统一由同目录的 `AGENTS.md` 维护，上面的导入将共享规则载入 Claude Code。

## 任务入口

- 从本目录启动会话，或先确认工作目录。这里的 `backend/`、`frontend/`、`docs/` 均相对于 `03ResultsFile/`，不要与同级 `03Agent/` 混用。
- 处理接口或联调问题时，先读 `docs/API_CONTRACT.md`，再对照 `backend/main.py` 和 `frontend/static/js/api.js`。
- 处理页面问题时，结合 `frontend/index.html`、对应的业务脚本和 `frontend/static/css/style.css` 定位，保留现有脚本加载顺序与 DOM 绑定。
- 处理模型或地图工具问题时，先区分配置缺失、LLM 响应、MCP 连接、工具调用和前端流式解析，不用修改无关模块掩盖错误。

## 维护方式

- 新增适用于所有编码助手的长期规则时，更新 `AGENTS.md`；本文件只保留 Claude Code 入口和阅读提示。
- 不自动导入整个源码目录、运行配置或历史提示词；按当前任务读取所需文件，避免把敏感配置和无关内容带入上下文。
- 任务结束用中文报告实际修改与已执行的验证，明确区分语法检查、模拟测试和真实服务联调。
