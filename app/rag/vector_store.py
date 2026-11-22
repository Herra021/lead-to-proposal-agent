import os
import glob
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from fastembed import TextEmbedding
from langchain_text_splitters import MarkdownHeaderTextSplitter

QDRANT_PATH = "./storage/qdrant_db"
COLLECTION_NAME = "cloudscale_docs"

# Initialize local embedding model (downloads once ~130MB, runs fast on CPU)
embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")

def get_qdrant_client() -> QdrantClient:
    return QdrantClient(path=QDRANT_PATH)

def ingest_documents():
    client = get_qdrant_client()
    
    # Recreate collection cleanly
    if client.collection_exists(COLLECTION_NAME):
        client.delete_collection(COLLECTION_NAME)
        
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE),
    )

    headers_to_split_on = [("#", "DocTitle"), ("##", "Section")]
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)

    points = []
    point_id = 1

    for filepath in glob.glob("./data/*.md"):
        filename = os.path.basename(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = splitter.split_text(content)
        texts = [c.page_content for c in chunks]
        embeddings = list(embedder.embed(texts))

        for chunk, vector in zip(chunks, embeddings):
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload={
                        "source_file": filename,
                        "doc_title": chunk.metadata.get("DocTitle", ""),
                        "section": chunk.metadata.get("Section", ""),
                        "text": chunk.page_content,
                    },
                )
            )
            point_id += 1

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"✅ Successfully ingested {len(points)} chunks into Qdrant.")

def search_knowledge_base(query: str, top_k: int = 4) -> list[dict]:
    client = get_qdrant_client()
    try:
        query_vector = list(embedder.embed([query]))[0].tolist()
        response = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            limit=top_k,
        )
        return [
            {
                "source": hit.payload.get("source_file", "doc.md"),
                "section": hit.payload.get("section", "General"),
                "text": hit.payload.get("text", ""),
                "score": round(hit.score, 3),
            }
            for hit in response.points
        ]
    finally:
        client.close()

if __name__ == "__main__":
    ingest_documents()
