import json
from pathlib import Path
from langchain.tools import tool

_BASE_FILE = Path(__file__).parent.parent / "data" / "cutting_params.json"
_USER_FILE = Path(__file__).parent.parent / "data" / "user_params.json"

_TOOL_ALIASES = {
    "平铣刀": "平刀", "立铣刀": "平刀", "flat": "平刀",
    "ball": "球刀", "球头刀": "球刀", "球铣刀": "球刀",
    "圆角刀": "牛鼻刀", "圆鼻刀": "牛鼻刀", "bull": "牛鼻刀",
}

_OP_ALIASES = {
    "粗加工": "粗铣", "开粗": "粗铣", "rough": "粗铣",
    "半精加工": "半精铣", "semi": "半精铣",
    "精加工": "精铣", "finish": "精铣",
}


def _load() -> dict:
    base = json.loads(_BASE_FILE.read_text(encoding="utf-8"))
    if _USER_FILE.exists():
        user = json.loads(_USER_FILE.read_text(encoding="utf-8"))
        # 用户自定义参数深度合并，不整体覆盖
        for mat, ops in user.items():
            if mat not in base:
                base[mat] = ops
            else:
                for op, tools in ops.items():
                    if op not in base[mat]:
                        base[mat][op] = tools
                    else:
                        base[mat][op].update(tools)
    return base


def _normalize(value: str, aliases: dict) -> str:
    v = value.strip()
    return aliases.get(v, v)


@tool
def recommend_params(
    material: str,
    operation: str,
    tool_type: str = "球刀",
    tool_diameter: float = 10.0,
) -> str:
    """
    推荐切削参数，支持 15+ 种模具材料和三种刀具类型。
    material: 材料名，如 P20 / 718H / S136 / NAK80 / DC53 / H13 / SKD11 /
              45号钢 / 铝合金7075 / 铜合金 / 2344 / 8407 / Cr12MoV / GS738 / 2316
    operation: 粗铣 / 半精铣 / 精铣（也支持：粗加工/开粗/精加工等别名）
    tool_type: 平刀 / 球刀 / 牛鼻刀（也支持别名）
    tool_diameter: 刀具直径 mm，默认 10.0
    """
    params = _load()
    op_norm  = _normalize(operation, _OP_ALIASES)
    tt_norm  = _normalize(tool_type, _TOOL_ALIASES)

    mat_key = next((k for k in params if k.upper() == material.upper()), None)
    if not mat_key:
        available = " / ".join(params.keys())
        return f"暂无 [{material}] 数据。\n当前支持：{available}"

    mat_data = params[mat_key]
    op_key = next(
        (k for k in mat_data if k not in ("硬度HRC", "加工性") and op_norm in k),
        None,
    )
    if not op_key:
        ops = [k for k in mat_data if k not in ("硬度HRC", "加工性")]
        return f"[{mat_key}] 不支持操作 [{operation}]。\n可用：{' / '.join(ops)}"

    tt_key = next((k for k in mat_data[op_key] if tt_norm in k), None)
    if not tt_key:
        tts = list(mat_data[op_key].keys())
        return f"不支持刀具类型 [{tool_type}]。\n可用：{' / '.join(tts)}"

    p = mat_data[op_key][tt_key]

    # 刀径修正（基准直径 10mm）
    r = 10.0 / max(tool_diameter, 0.1)
    rpm_lo  = int(p["rpm"][0]  * r)
    rpm_hi  = int(p["rpm"][1]  * r)
    feed_lo = int(p["feed"][0] / r)
    feed_hi = int(p["feed"][1] / r)

    hardness = mat_data.get("硬度HRC", "—")
    note     = mat_data.get("加工性", "")

    return (
        f"【{mat_key} / {op_key} / {tt_key} D{tool_diameter}】\n"
        f"  硬度：{hardness} HRC\n"
        f"  主轴转速：{rpm_lo} ~ {rpm_hi} rpm\n"
        f"  进给速度：{feed_lo} ~ {feed_hi} mm/min\n"
        f"  切削深度：{p['depth'][0]} ~ {p['depth'][1]} mm\n"
        f"  材料说明：{note}\n"
        f"  ⚠ 以上为参考值，实际需根据机床刚性和刀具状态调整"
    )


@tool
def list_materials() -> str:
    """列出所有支持的模具材料及简要说明。"""
    params = _load()
    lines = ["【支持的材料列表】\n"]
    for mat, data in params.items():
        hardness = data.get("硬度HRC", "—")
        note     = data.get("加工性", "")[:28]
        src      = "（自定义）" if _USER_FILE.exists() and mat in json.loads(
            _USER_FILE.read_text(encoding="utf-8")
        ) else ""
        lines.append(f"  {mat:<12} HRC {hardness:<16} {note}… {src}")
    return "\n".join(lines)


@tool
def save_custom_params(
    material: str,
    operation: str,
    tool_type: str,
    rpm_low: int,
    rpm_high: int,
    feed_low: int,
    feed_high: int,
    depth_low: float,
    depth_high: float,
    note: str = "",
) -> str:
    """
    保存用户自定义切削参数到本地，下次推荐时优先使用。
    适用于：新材料录入 / 覆盖默认参数 / 沉淀工厂实际经验。
    """
    _USER_FILE.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if _USER_FILE.exists():
        data = json.loads(_USER_FILE.read_text(encoding="utf-8"))

    entry = {
        "rpm":   [rpm_low,   rpm_high],
        "feed":  [feed_low,  feed_high],
        "depth": [depth_low, depth_high],
    }
    data.setdefault(material, {}).setdefault(operation, {})[tool_type] = entry
    if note:
        data[material]["加工性"] = note

    _USER_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return (
        f"✓ 已保存 [{material} / {operation} / {tool_type}]\n"
        f"  转速 {rpm_low}~{rpm_high} rpm，进给 {feed_low}~{feed_high} mm/min，"
        f"切深 {depth_low}~{depth_high} mm\n"
        f"  下次调用 recommend_params 时将优先使用此参数"
    )
