"""
导入工艺文档到本地向量知识库。

用法：
  python -m rag.ingest --dir  data/docs          # 批量导入文件夹
  python -m rag.ingest --text "内容" --source "来源"  # 手动录入
  python -m rag.ingest --stats                   # 查看知识库状态
"""
import argparse
from pathlib import Path
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rag.knowledge_base import add_documents, get_stats


def _splitter() -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=400,
        chunk_overlap=60,
        separators=["\n\n", "\n", "。", "；", " ", ""],
    )


def ingest_directory(directory: str) -> str:
    path = Path(directory)
    docs: list[Document] = []
    for file in path.rglob("*"):
        try:
            if file.suffix.lower() == ".pdf":
                docs.extend(PyPDFLoader(str(file)).load())
            elif file.suffix.lower() in (".txt", ".md", ".nc", ".gcode"):
                docs.extend(TextLoader(str(file), encoding="utf-8").load())
        except Exception as e:
            print(f"跳过 {file.name}：{e}")

    if not docs:
        return "未找到可导入文件（支持 .pdf .txt .md .nc .gcode）"

    chunks = _splitter().split_documents(docs)
    n = add_documents(chunks)
    return f"✓ 导入完成：{len(docs)} 个文件 → {n} 个片段"


def ingest_text(text: str, source: str = "手工录入") -> str:
    doc    = Document(page_content=text, metadata={"source": source})
    chunks = _splitter().split_documents([doc])
    n      = add_documents(chunks)
    return f"✓ 录入 {n} 个片段，来源：{source}"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir",    help="导入文件夹路径")
    parser.add_argument("--text",   help="直接录入文本内容")
    parser.add_argument("--source", default="手工录入", help="来源标注")
    parser.add_argument("--stats",  action="store_true", help="查看知识库状态")
    args = parser.parse_args()

    if args.stats:
        info = get_stats()
        print(f"  知识条目总数：{info['total']}")
        print(f"  向量库路径  ：{info['db_path']}")
        print(f"  Embedding   ：{info['embed_model']}")
    elif args.dir:
        print(ingest_directory(args.dir))
    elif args.text:
        print(ingest_text(args.text, args.source))
    else:
        parser.print_help()
