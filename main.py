from dotenv import load_dotenv
load_dotenv()

import json
import time
import tempfile
from pathlib import Path

import gradio as gr
from langchain_core.messages import HumanMessage, AIMessage

from agent.agent_core import build_agent
from tools.gcode_analyzer import analyze_gcode
from tools.doc_generator import generate_process_doc
from rag.knowledge_base import get_stats
from rag.ingest import ingest_directory, ingest_text

# ── 历史对话存储目录 ──────────────────────────────────────
_HISTORY_DIR = Path("history")
_HISTORY_DIR.mkdir(exist_ok=True)

agent = build_agent()


# ══════════════════════════════════════════════════════════
# 对话模式
# ══════════════════════════════════════════════════════════

def chat_stream(message: str, history: list):
    """流式输出：逐 token 返回，Gradio 自动渲染打字效果"""
    lc_history = []
    for msg in history:
        if isinstance(msg, dict):
            # Gradio 5.0+ 格式：{"role": "user"/"assistant", "content": "..."}
            if msg["role"] == "user":
                lc_history.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "assistant":
                lc_history.append(AIMessage(content=msg["content"]))
        else:
            # 兼容旧格式：[user_msg, ai_msg]
            h, a = msg
            lc_history.append(HumanMessage(content=h))
            lc_history.append(AIMessage(content=a))

    # AgentExecutor 不直接支持流式，用 stream_events 模拟
    full_response = ""
    try:
        for chunk in agent.stream({"input": message, "chat_history": lc_history}):
            # chunk 可能是 dict 含 output，也可能是中间步骤
            if "output" in chunk:
                token = chunk["output"]
                # 去掉已经 yield 过的部分，只追加新增内容
                new_part = token[len(full_response):]
                full_response = token
                yield {"role": "assistant", "content": full_response}
    except Exception as e:
        yield {"role": "assistant", "content": f"[错误] {e}"}


def save_history(history: list, session_name: str) -> str:
    """保存当前对话到 history/ 目录"""
    if not history:
        return "对话为空，无需保存"
    name = session_name.strip() or f"session_{int(time.time())}"
    name = name.replace("/", "_").replace("\\", "_")
    path = _HISTORY_DIR / f"{name}.json"
    path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return f"✓ 已保存至 history/{name}.json"


def load_history_list() -> list[str]:
    """返回所有已保存对话的文件名列表"""
    return [f.stem for f in sorted(_HISTORY_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)]


def load_history(session_name: str) -> tuple[list, str]:
    """加载指定对话记录"""
    if not session_name:
        return [], "请先选择一条历史记录"
    path = _HISTORY_DIR / f"{session_name}.json"
    if not path.exists():
        return [], f"未找到 {session_name}"
    history = json.loads(path.read_text(encoding="utf-8"))
    return history, f"✓ 已加载 {session_name}（{len(history)} 轮对话）"

def refresh_history_list():
    return gr.update(choices=load_history_list())


# ══════════════════════════════════════════════════════════
# 文件审查模式
# ══════════════════════════════════════════════════════════

def analyze_file(file, machine_type: str) -> str:
    if file is None:
        return "请上传 G 代码文件"
    content = Path(file.name).read_text(encoding="utf-8", errors="ignore")
    analysis = analyze_gcode.invoke({"gcode": content, "machine_type": machine_type})
    doc      = generate_process_doc.invoke(content)
    return f"{analysis}\n\n{doc}"


def export_pdf(report_text: str):
    if not report_text.strip():
        return None
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        import os

        # 中文字体查找（Linux / Windows / macOS）
        font_candidates = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "/System/Library/Fonts/PingFang.ttc",
        ]
        font_name = "Helvetica"
        for fp in font_candidates:
            if os.path.exists(fp):
                pdfmetrics.registerFont(TTFont("CJK", fp))
                font_name = "CJK"
                break

        tmp  = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        c    = canvas.Canvas(tmp.name, pagesize=A4)
        w, h = A4
        c.setFont(font_name, 11)
        y = h - 48
        for line in report_text.split("\n"):
            if y < 48:
                c.showPage()
                c.setFont(font_name, 11)
                y = h - 48
            c.drawString(40, y, line)
            y -= 17
        c.save()
        return tmp.name
    except Exception as e:
        print(f"PDF 导出失败：{e}")
        return None


# ══════════════════════════════════════════════════════════
# 知识库管理
# ══════════════════════════════════════════════════════════

def _fmt_stats() -> str:
    info = get_stats()
    return (
        f"知识条目总数：{info['total']}\n"
        f"向量库路径  ：{info['db_path']}\n"
        f"Embedding   ：{info['embed_model']}"
    )


def kb_ingest_folder(folder_path: str) -> str:
    p = Path(folder_path.strip())
    if not p.exists():
        return f"路径不存在：{folder_path}"
    msg = ingest_directory(str(p))
    return f"{msg}\n\n{_fmt_stats()}"


def kb_ingest_text(text: str, source: str) -> str:
    if not text.strip():
        return "请输入知识内容"
    msg = ingest_text(text.strip(), source.strip() or "手工录入")
    return f"{msg}\n\n{_fmt_stats()}"


# ══════════════════════════════════════════════════════════
# Gradio UI
# ══════════════════════════════════════════════════════════

with gr.Blocks(title="模具编程 AI 助手") as demo:
    gr.Markdown("## 模具编程 AI 助手 v0.3")

    # ── Tab 1：对话模式 ────────────────────────────────────
    with gr.Tab("对话模式"):
        chatbot = gr.Chatbot(height=500, label="对话记录")
        msg_box = gr.Textbox(
            placeholder="输入问题，例如：P20 精铣 D10 球刀推荐参数",
            label="输入",
            lines=2,
        )
        with gr.Row():
            submit_btn = gr.Button("发送", variant="primary")
            clear_btn  = gr.Button("清空对话")

        gr.Examples(
            examples=[
                "列出所有支持的材料",
                "P20 粗铣 D16 牛鼻刀推荐参数",
                "718H 精铣 D8 球刀，然后换成半精铣",
                "DC53 和 Cr12MoV 在切削难度上有什么区别？",
                "帮我分析：\nG00 Z-50\nS9000 M03\nG01 X100 F0\nM05\nG01 Y50 F300",
            ],
            inputs=msg_box,
        )

        gr.Markdown("#### 历史对话")
        with gr.Row():
            session_name_input = gr.Textbox(
                placeholder="保存名称（留空自动生成）", label="会话名称", scale=2
            )
            save_btn    = gr.Button("保存对话", scale=1)
            refresh_btn = gr.Button("刷新列表", scale=1)

        history_dropdown = gr.Dropdown(
            choices=load_history_list(), label="已保存的对话", interactive=True
        )
        with gr.Row():
            load_btn   = gr.Button("加载对话")
            status_box = gr.Textbox(label="操作状态", interactive=False, scale=3)


            # 事件绑定
            def _submit(message, history):
                # 先把用户消息加到 history 显示
                if message.strip():
                    history = history + [{"role": "user", "content": message}]
                return "", history


            def _bot(history):
                if not history:
                    return history

                # 确保最后一条是用户消息
                last_message = history[-1]
                if last_message.get("role") != "user":
                    return history

                message = last_message["content"]

                # 调用流式生成
                bot_message = ""
                try:
                    for chunk in agent.stream({"input": message, "chat_history": []}):
                        if "output" in chunk:
                            bot_message = chunk["output"]
                            # 创建新的历史记录列表，更新最后一条为 AI 回复
                            new_history = history[:-1] + [{"role": "assistant", "content": bot_message}]
                            yield new_history
                except Exception as e:
                    error_history = history[:-1] + [{"role": "assistant", "content": f"[错误] {e}"}]
                    yield error_history


            msg_box.submit(_submit, [msg_box, chatbot], [msg_box, chatbot], queue=False).then(
                _bot, chatbot, chatbot
            )
            submit_btn.click(_submit, [msg_box, chatbot], [msg_box, chatbot], queue=False).then(
                _bot, chatbot, chatbot
            )
            clear_btn.click(lambda: [], None, chatbot)
        save_btn.click(save_history, [chatbot, session_name_input], status_box)
        refresh_btn.click(refresh_history_list, outputs=history_dropdown)
        load_btn.click(load_history, history_dropdown, [chatbot, status_box])

    # ── Tab 2：文件审查 ────────────────────────────────────
    with gr.Tab("文件审查"):
        gr.Markdown("上传 G 代码文件，自动生成分级审查报告")
        with gr.Row():
            file_input = gr.File(
                label="上传 G 代码",
                file_types=[".nc", ".gcode", ".txt"],
            )
            machine_sel = gr.Radio(
                ["fanuc", "siemens", "mitsubishi"],
                value="fanuc",
                label="机床类型",
            )
        report_box = gr.Textbox(label="审查报告", lines=24, interactive=False)
        with gr.Row():
            run_btn = gr.Button("开始审查", variant="primary")
            pdf_btn = gr.Button("导出 PDF")
            pdf_file = gr.File(label="下载报告", visible=False)

        run_btn.click(analyze_file, [file_input, machine_sel], report_box)
        pdf_btn.click(export_pdf, report_box, pdf_file).then(
            lambda f: gr.update(visible=f is not None), pdf_file, pdf_file
        )

        # ── Tab 3：知识库管理 ──────────────────────────────────
        with gr.Tab("知识库管理"):
            gr.Markdown("### 导入工艺文档到本地知识库")
            stats_box = gr.Textbox(
                label="当前知识库状态",
                lines=3,
                interactive=False,
                value=_fmt_stats(),
            )

            gr.Markdown("**方式一：批量导入文件夹**（支持 .pdf .txt .md .nc .gcode）")
            with gr.Row():
                folder_input = gr.Textbox(
                    label="文件夹路径",
                    placeholder="data/docs 或绝对路径",
                    scale=3,
                )
                folder_btn = gr.Button("导入", variant="primary", scale=1)

        gr.Markdown("**方式二：手动录入单条知识**")
        with gr.Row():
            text_input = gr.Textbox(
                label="知识内容",
                lines=4,
                placeholder="例：718H 高光精铣推荐使用涂层球刀，转速 2000-2500rpm…",
                scale=3,
            )
            source_input = gr.Textbox(
                label="来源标注",
                placeholder="例：张师傅经验 / 工艺规范2024",
                scale=1,
            )
        text_btn = gr.Button("录入知识")
        text_btn.click(kb_ingest_text, [text_input, source_input], stats_box)

        gr.Button("刷新状态").click(_fmt_stats, outputs=stats_box)


if __name__ == "__main__":
    demo.queue()   # 开启队列以支持流式输出
    demo.launch(server_name="localhost", server_port=7860, share=False, theme=gr.themes.Soft())