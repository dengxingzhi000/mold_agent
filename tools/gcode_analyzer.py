import re
from langchain.tools import tool

MACHINE_RULES = {
    "fanuc": {
        "max_spindle": 8000,
        "max_feed": 10000,
        "coolant_on": "M08",
        "label": "发那科",
    },
    "siemens": {
        "max_spindle": 12000,
        "max_feed": 15000,
        "coolant_on": "M08",
        "label": "西门子840D",
    },
    "mitsubishi": {
        "max_spindle": 10000,
        "max_feed": 12000,
        "coolant_on": "M08",
        "label": "三菱",
    },
}


@tool
def analyze_gcode(gcode: str, machine_type: str = "fanuc") -> str:
    """
    审查 G 代码安全性，输出带行号的分级报告。
    gcode: G 代码文本
    machine_type: 机床类型，支持 fanuc / siemens / mitsubishi，默认 fanuc
    """
    machine = MACHINE_RULES.get(machine_type.lower(), MACHINE_RULES["fanuc"])
    lines = gcode.strip().split("\n")

    errors, warnings, infos = [], [], []
    spindle_on = False
    tool_changes: list[str] = []
    max_spindle_seen = 0
    max_feed_seen = 0
    prev_feed: float | None = None
    coolant_used = False

    for i, raw in enumerate(lines, 1):
        line = raw.strip().upper()
        if not line or line.startswith(("(", "%", ";")):
            continue

        # ── 状态跟踪 ──────────────────────────────────────
        if re.search(r"\bM0?[34]\b", line):
            spindle_on = True
        if re.search(r"\bM0?5\b", line):
            spindle_on = False
        if machine["coolant_on"] in line:
            coolant_used = True

        t = re.search(r"\bT(\d+)\b", line)
        if t and re.search(r"\bM0?6\b", line):
            tool_changes.append(f"T{t.group(1)}")

        # ── 数值提取 ──────────────────────────────────────
        s_val = _num(line, "S")
        f_val = _num(line, "F")
        z_val = _num(line, "Z")

        if s_val is not None:
            max_spindle_seen = max(max_spindle_seen, s_val)
        if f_val is not None:
            max_feed_seen = max(max_feed_seen, f_val)

        is_cut = bool(re.search(r"\bG0?[123]\b", line))
        is_rapid = bool(re.search(r"\bG0{1,2}\b", line))

        # ══ 错误（必须处理）══════════════════════════════

        # E1 快速移动 Z 轴过低
        if is_rapid and z_val is not None and z_val < 5:
            errors.append(f"[E] L{i}: G00 快速定位 Z={z_val}mm，低于安全高度 5mm，碰刀风险")

        # E2 切削时主轴未启动
        if is_cut and not spindle_on:
            errors.append(f"[E] L{i}: 主轴未启动，执行切削指令 → {raw.strip()}")

        # E3 进给为零
        if f_val == 0:
            errors.append(f"[E] L{i}: 进给速度 F=0，机床将停止进给")

        # E4 超出机床额定转速
        if s_val is not None and s_val > machine["max_spindle"]:
            errors.append(
                f"[E] L{i}: S={int(s_val)} 超出{machine['label']}额定转速"
                f" {machine['max_spindle']} rpm"
            )

        # E5 超出机床额定进给
        if f_val is not None and f_val > machine["max_feed"]:
            errors.append(
                f"[E] L{i}: F={int(f_val)} 超出{machine['label']}额定进给"
                f" {machine['max_feed']} mm/min"
            )

        # ══ 警告（建议关注）══════════════════════════════

        # W1 进给突变超 60%
        if f_val is not None and prev_feed and prev_feed > 0:
            ratio = abs(f_val - prev_feed) / prev_feed
            if ratio > 0.6:
                warnings.append(
                    f"[W] L{i}: 进给从 {int(prev_feed)} 突变为 {int(f_val)}"
                    f"（变幅 {ratio:.0%}），建议平滑过渡"
                )
        if f_val is not None:
            prev_feed = f_val

        # W2 缺刀补（仅提示一次）
        if is_cut and i == 1:
            if "G41" not in gcode.upper() and "G42" not in gcode.upper():
                warnings.append("[W] 全程未检测到刀具半径补偿 G41/G42，精加工轮廓建议开启")

    # W3 切削全程无冷却
    if not coolant_used and max_spindle_seen > 0:
        warnings.append(
            f"[W] 全程未检测到冷却液指令（{machine['coolant_on']}），"
            "建议开启冷却防止积热"
        )

    # ── 统计 ──────────────────────────────────────────────
    infos = [
        f"扫描行数：{len(lines)} 行",
        f"换刀次数：{len(tool_changes)} 次 ({', '.join(tool_changes) or '无'})",
        f"最高转速：{max_spindle_seen} rpm",
        f"最高进给：{max_feed_seen} mm/min",
        f"机床类型：{machine['label']}",
    ]

    parts = ["══════ G 代码审查报告 ══════"]
    parts.append("【统计信息】\n" + "\n".join(f"  {x}" for x in infos))
    if errors:
        parts.append(
            f"【错误 × {len(errors)}】必须处理\n" + "\n".join(f"  {x}" for x in errors)
        )
    else:
        parts.append("【错误】✓ 无")
    if warnings:
        parts.append(
            f"【警告 △ {len(warnings)}】建议关注\n"
            + "\n".join(f"  {x}" for x in warnings)
        )
    else:
        parts.append("【警告】✓ 无")
    parts.append("（报告由 AI 自动生成，上机前请人工复核）")
    return "\n\n".join(parts)


def _num(line: str, key: str) -> float | None:
    m = re.search(rf"\b{key}(-?\d+\.?\d*)", line)
    return float(m.group(1)) if m else None
