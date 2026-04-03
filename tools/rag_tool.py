from langchain.tools import tool
from rag.knowledge_base import search_knowledge, get_stats


@tool
def query_knowledge_base(question: str) -> str:
    """
    从本地模具工艺知识库检索相关内容。
    适用于：工艺规范查询、历史案例参考、特殊材料经验。
    知识库为空时会给出导入提示。
    """
    stats = get_stats()
    if stats["total"] == 0:
        return (
            "知识库当前为空，请先导入工艺文档：\n"
            "  python -m rag.ingest --dir data/docs\n"
            "  python -m rag.ingest --text '内容' --source '来源'"
        )

    docs = search_knowledge(question, k=3)
    if not docs:
        return "知识库中未检索到相关内容，建议向有经验的师傅确认。"

    parts = [f"【知识库检索（共 {stats['total']} 条）】"]
    for i, doc in enumerate(docs, 1):
        src = doc.metadata.get("source", "未知来源")
        parts.append(f"\n[{i}] 来源：{src}\n{doc.page_content.strip()}")
    return "\n".join(parts)
