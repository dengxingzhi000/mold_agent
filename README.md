<div align="center">

# mold_agent

### 模具数控编程 AI 助手 —— G 代码审查、切削参数推荐与工艺知识库。

**面向模具厂 CNC 编程工程师的本地助手。基于 DeepSeek + LangChain，
知识库与对话历史全部落在本地，Gradio 界面开箱即用。**

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?labelColor=black&style=flat-square&logo=python)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](./LICENSE)

[快速开始](#快速开始) · [三种模式](#三种模式) · [工具](#工具) · [项目结构](#项目结构) · [FAQ](#faq)

<code>pip install -r requirements.txt &amp;&amp; python main.py</code>

</div>

> [!WARNING]
> **仓库缺少 `data/cutting_params.json`，全新克隆后参数相关工具会直接报错。**
> `.gitignore` 第 28 行忽略了整个 `data/` 目录，但 `tools/param_advisor.py`
> 的 `_load()` 会无条件读取 `data/cutting_params.json`，缺失时抛
> `FileNotFoundError`。`list_materials`、`recommend_params`、
> `save_custom_params` 三个工具因此不可用，直到你自行补上该文件。
> `data/user_params.json` 不存在是正常的 —— 它由 `save_custom_params` 自动创建。

---

数控编程里最费时间的往往不是写 G 代码，而是确认参数：这块 P20 精铣用 D10 球刀
转速给多少、转速给完进给给多少、程序里有没有会撞刀的地方。这些答案分散在老师傅
的经验、机床手册和厂里的工艺规范里，很少有人愿意每次都去翻。

`mold_agent` 把这些经验做成一个本地 Agent：内置材料 × 刀具的切削参数表，
能审查 G 代码并标注危险指令，能按材料/工序/刀具推荐具体转速进给，
还能查本地工艺知识库、生成加工工序单并导出 PDF。数据全部留在本机。

## 快速开始

### 前置依赖

- **Python 3.10+**
- **DeepSeek API Key** —— 必填，无降级路径

### 安装与运行

```bash
git clone https://github.com/dengxingzhi000/mold_agent.git
cd mold_agent

pip install -r requirements.txt

# 配置 API Key（仓库中没有 .env.example，请手动创建）
echo DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx > .env

python main.py
```

随后打开 <http://localhost:7860>。界面为 Gradio，三个标签页分别是
**对话模式**、**文件审查**、**知识库管理**。

> [!NOTE]
> **`.env` 已被 `.gitignore` 忽略，不要提交。** 仓库中不存在 `.env.example`
> 模板，唯一必需的环境变量是 `DEEPSEEK_API_KEY`。

## 三种模式

| 模式           | 做什么                                                                   | 输入 / 输出                                                           |
| -------------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| **对话模式**   | 流式问答，自动携带上文中的材料、机床、刀具、刀径，支持保存与加载历史会话 | 自然语言；历史写入 `history/*.json`                                   |
| **文件审查**   | 上传 G 代码文件，按机床类型生成安全审查报告，可导出 PDF                  | `.nc` / `.gcode` / `.txt`；输出审查报告 + PDF                         |
| **知识库管理** | 把工艺文档导入本地向量库，或手工录入单条知识并标注来源                   | 文件夹批量导入或单条录入；实时显示条目数、向量库路径与 embedding 模型 |

### 文件审查支持的机床类型

`fanuc`（默认） · `siemens` · `mitsubishi`

### 知识库支持的导入格式

批量导入文件夹支持 `.pdf` `.txt` `.md` `.nc` `.gcode`；
也可以手工录入单条知识并填写来源标注（如「张师傅经验」「工艺规范2024」）。

## 工具

Agent 通过 6 个 LangChain tool 完成工作，由 `agent/agent_core.py` 统一注册：

| 工具                   | 用途               | 说明                                           |
| ---------------------- | ------------------ | ---------------------------------------------- |
| `analyze_gcode`        | G 代码安全审查     | 发现风险时明确标注 `[⚠ 危险]`，不含糊带过      |
| `recommend_params`     | 切削参数推荐       | 按材料 × 工序 × 刀具推荐具体转速与进给         |
| `list_materials`       | 查询支持的材料列表 | 内置 15+ 种材料                                |
| `save_custom_params`   | 保存工厂自定义参数 | 写入 `data/user_params.json`，与内置表深度合并 |
| `generate_process_doc` | 生成加工工序单     | 按材料/工序/刀具组织                           |
| `query_knowledge_base` | 检索本地工艺知识库 | 涉及工艺规范或历史案例时优先调用               |

### 别名归一化

为了容错，工具名与工序名都做了别名映射（`tools/param_advisor.py`）：

| 输入                   | 归一化为 |
| ---------------------- | -------- |
| 平铣刀 / 立铣刀 / flat | 平刀     |
| ball / 球头刀 / 球铣刀 | 球刀     |
| 圆角刀 / 圆鼻刀 / bull | 牛鼻刀   |
| 粗加工 / 开粗 / rough  | 粗铣     |
| 半精加工 / semi        | 半精铣   |
| 精加工 / finish        | 精铣     |

> [!TIP]
> **Agent 会沿用上下文。** 你说「718H 精铣 D10 球刀」，下一句说「换粗铣」时，
> 它会保持材料、刀具、刀径不变只改工序。这是 `SYSTEM_PROMPT` 中显式定义的
> 上下文记忆规则（`agent/agent_core.py`）。

## 项目结构

```text
mold_agent/
├── main.py                  Gradio 界面入口（三个标签页 + PDF 导出 + 会话管理）
├── agent/
│   ├── agent_core.py        构建 Agent：DeepSeek 模型 + 6 个工具 + 系统提示词
│   └── __init__.py
├── tools/
│   ├── gcode_analyzer.py    G 代码安全审查
│   ├── param_advisor.py     切削参数推荐与自定义参数持久化
│   ├── doc_generator.py     加工工序单生成
│   ├── rag_tool.py          知识库检索工具封装
│   └── __init__.py          统一导出上述工具
├── rag/
│   ├── ingest.py            文档批量导入与单条录入
│   ├── knowledge_base.py    Chroma 向量库封装与状态统计
│   └── __init__.py
├── data/                    ⚠ 被 gitignore，但代码依赖其中的 cutting_params.json
├── history/                 会话历史 JSON（运行时生成）
└── requirements.txt
```

### 依赖

`langchain` · `langchain-openai` · `langchain-chroma` · `langchain-community` ·
`langchain-text-splitters` · `chromadb` · `sentence-transformers` ·
`gradio` · `reportlab` · `pypdf` · `python-dotenv`

模型为 `deepseek-chat`（`https://api.deepseek.com`），`temperature=0.1`，
经 `langchain-openai` 的 `ChatOpenAI` 调用。

## FAQ

<details>
<summary><strong>为什么必须配 DeepSeek Key？没有离线模式吗？</strong></summary>

没有。`agent/agent_core.py` 中直接 `os.getenv("DEEPSEEK_API_KEY")` 传给
`ChatOpenAI`，没有默认值也没有降级路径，未配置时会抛
`ValidationError`。知识库和向量库都是本地的，但推理必须调用模型。

</details>

<details>
<summary><strong>克隆下来就报 FileNotFoundError 怎么办？</strong></summary>

多半是缺 `data/cutting_params.json`。该文件被 `.gitignore` 的 `data/` 规则忽略，
没有提交到仓库，而 `tools/param_advisor.py` 的 `_load()` 会无条件读取它。
需要自行准备该文件，结构为「材料 → 工序 → 刀具 → 参数」的嵌套 JSON。

`data/user_params.json` 缺失则是正常的，会在首次调用 `save_custom_params` 时自动创建。

</details>

<details>
<summary><strong>怎么让 Agent 用厂里自己的参数而不是内置值？</strong></summary>

让 Agent 调用 `save_custom_params` 写入 `data/user_params.json`。该文件在加载时
与内置表**深度合并**而非整体覆盖：同名材料/工序下的刀具条目会被逐个 update，
所以只补充差异项即可，不必复制整张表。

</details>

<details>
<summary><strong>PDF 导出的中文字体怎么处理的？</strong></summary>

`main.py` 的 `export_pdf()` 按顺序查找文泉驿正黑、Noto Sans CJK、
Windows 的 `simhei.ttf` / `msyh.ttc`、macOS 的 PingFang。找不到时回退到
Helvetica，此时中文会显示为方块。

</details>

## 贡献

欢迎贡献：fork → 新分支 → 提交 → 发起 PR。

## 作者

- Deng &lt;a2015055080@163.com&gt;

## 许可证

本项目使用 MIT 许可证，详见 [LICENSE](./LICENSE)。
