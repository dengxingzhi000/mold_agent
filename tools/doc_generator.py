import re
from langchain.tools import tool


@tool
def generate_process_doc(gcode: str) -> str:
    """
    解析 G 代码，自动生成加工工序单摘要。
    输入 G 代码文本，输出结构化工序描述。
    """
    lines = gcode.strip().split("\n")
    tool_changes: list[str] = []
    max_spindle = 0
    max_feed    = 0
    coolant     = False
    cut_moves   = 0
    rapid_moves = 0

    for raw in lines:
        line = raw.strip().upper()
        if not line or line.startswith(("(", "%", ";")):
            continue

        t = re.search(r"\bT(\d+)\b", line)
        if t and re.search(r"\bM0?6\b", line):
            tool_changes.append(f"T{t.group(1)}")

        s = re.search(r"\bS(\d+)\b", line)
        if s:
            max_spindle = max(max_spindle, int(s.group(1)))

        f = re.search(r"\bF(\d+\.?\d*)\b", line)
        if f:
            max_feed = max(max_feed, float(f.group(1)))

        if "M08" in line:
            coolant = True
        if re.search(r"\bG0{1,2}\b", line):
            rapid_moves += 1
        if re.search(r"\bG0?[123]\b", line):
            cut_moves += 1

    doc = [
        "═══ 加工工序单（AI 自动生成）═══",
        f"总代码行数   ：{len(lines)} 行",
        f"快速定位次数 ：{rapid_moves} 次",
        f"切削指令次数 ：{cut_moves} 次",
        f"换刀次数     ：{len(tool_changes)} 次 ({', '.join(tool_changes) or '无'} )",
        f"最高主轴转速 ：{max_spindle} rpm",
        f"最高进给速度 ：{max_feed} mm/min",
        f"冷却液       ：{'已开启（M08）' if coolant else '未检测到冷却指令'}",
        "",
        "⚠ 本工序单由 AI 自动解析，上机前请人工核对",
    ]
    return "\n".join(doc)
