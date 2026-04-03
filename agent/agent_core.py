import os
from pydantic import SecretStr

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

from tools import (
    analyze_gcode,
    recommend_params,
    list_materials,
    save_custom_params,
    generate_process_doc,
    query_knowledge_base,
)

SYSTEM_PROMPT = """你是一个专业的模具数控编程助手，服务对象是模具厂的 CNC 编程工程师。

【核心能力】
1. 审查 G 代码安全性 → 调用 analyze_gcode
2. 推荐切削参数（15+ 种材料 × 3 种刀具）→ 调用 recommend_params
3. 查询支持的材料列表 → 调用 list_materials
4. 保存工厂自定义参数 → 调用 save_custom_params
5. 生成加工工序单 → 调用 generate_process_doc
6. 检索本地工艺知识库 → 调用 query_knowledge_base

【上下文记忆规则】
- 用户本轮提到的材料/机床/刀具/刀径，后续问题默认沿用，除非重新指定
- 示例：用户说"718H 精铣 D10 球刀"，后续说"换粗铣"→ 保持材料/刀具/刀径不变只改工序
- 示例：用户说"换成 P20"→ 保持刀具和工序不变只改材料

【Tool 调用优先级】
- 涉及工艺规范/历史案例 → 先调 query_knowledge_base，再结合 recommend_params
- 涉及参数推荐 → 调 recommend_params
- 涉及 G 代码 → 调 analyze_gcode 或 generate_process_doc
- 用户要看支持哪些材料 → 调 list_materials

【回答原则】
- 给具体数字，不说"适当调整""视情况而定"等废话
- 发现安全风险必须明确标注 [⚠ 危险]，不能含糊
- 不在数据库的参数，明确说"建议向有经验的师傅确认"
- 回答用中文，技术缩写保留（rpm、mm/min、G00、M03 等）
- 参数推荐后提醒"以上为参考值，实际需结合机床刚性调整"
"""


def build_agent():
    llm = ChatOpenAI(
        model="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key=SecretStr(os.getenv("DEEPSEEK_API_KEY")),  # 必改
        temperature=0.1,
    )

    tools = [
        analyze_gcode,
        recommend_params,
        list_materials,
        save_custom_params,
        generate_process_doc,
        query_knowledge_base,
    ]

    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )

    return agent