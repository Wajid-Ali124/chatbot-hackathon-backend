from playwright.sync_api import sync_playwright
import trafilatura
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
import cohere

# -------------------------------------
# CONFIG
# -------------------------------------
# Your Deployment Link:
COLLECTION_NAME = "ai-powered-book"

cohere_client = cohere.Client("luJRwGder19unRrfQfGtMHWyV3dglMxha1RcmZTf")
EMBED_MODEL = "embed-english-v3.0"

# Connect to Qdrant Cloud
qdrant = QdrantClient(
    url="https://995fa902-d094-4ef7-81e0-2e8fd49de529.us-east4-0.gcp.cloud.qdrant.io:6333",
    api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.4VDKCb4BjUB6rWJGX0p1nelG6hFN47dACg9SSuAeqqk" 
)

urls = [
    "http://localhost:3000/docs/intro",
    "http://localhost:3000/docs/chapter1",
    "http://localhost:3000/docs/chapter2"    
    ]

# -------------------------------------
# Step 1 — Download page + extract text
# -------------------------------------
def extract_text_from_url(url, page):
    """Extract text using existing page instance"""
    try:
        print(f"Loading: {url}")
        
        # Use simpler wait condition
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        
        # Give it a moment for content to render
        page.wait_for_timeout(3000)
        
        html = page.content()
        text = trafilatura.extract(html)
        
        if not text:
            print("[WARNING] No text extracted from:", url)
        else:
            print(f"✓ Extracted {len(text)} characters")
        
        return text
    except Exception as e:
        print(f"[ERROR] Failed to process {url}: {str(e)}")
        return None

# -------------------------------------
# Step 2 — Chunk the text
# -------------------------------------
def chunk_text(text, max_chars=1200):
    chunks = []
    while text:
        if len(text) <= max_chars:
            chunks.append(text)
            break
            
        # Find last sentence boundary
        split_pos = text[:max_chars].rfind(". ")
        
        if split_pos == -1:  # No sentence boundary found
            split_pos = max_chars
        else:
            split_pos += 1  # Include the period
        
        chunks.append(text[:split_pos].strip())
        text = text[split_pos:].strip()
    
    return chunks

# -------------------------------------
# Step 3 — Create embedding
# -------------------------------------
def embed(text):
    response = cohere_client.embed(
        model=EMBED_MODEL,
        input_type="search_query",  # Use search_query for queries
        texts=[text],
    )
    return response.embeddings[0]  # Return the first embedding


# -------------------------------------
# Step 4 — Store in Qdrant
# -------------------------------------
def create_collection():
    print("\nCreating Qdrant collection...")
    qdrant.recreate_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
        size=1024,        # Cohere embed-english-v3.0 dimension
        distance=Distance.COSINE
        )
    )

def save_chunk_to_qdrant(chunk, chunk_id, url):
    print(f"  Creating embedding for chunk {chunk_id}...")
    vector = embed(chunk)
    
    print(f"  Uploading chunk {chunk_id} to Qdrant...")
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            PointStruct(
                id=chunk_id,
                vector=vector,
                payload={
                    "url": url,
                    "text": chunk,
                    "chunk_id": chunk_id
                }
            )
        ]
    )
    print(f"  ✓ Saved chunk {chunk_id}")


# -------------------------------------
# MAIN INGESTION PIPELINE
# -------------------------------------
def ingest_book():
    create_collection()
    global_id = 1
    
    # Create browser ONCE
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        for url in urls:
            print("\nProcessing:", url)
            text = extract_text_from_url(url, page)  # Pass page object
            
            if not text:
                continue
            
            chunks = chunk_text(text)
            
            for ch in chunks:
                save_chunk_to_qdrant(ch, global_id, url)
                print(f"Saved chunk {global_id}")
                global_id += 1
        
        browser.close()  # Close at the end
    
    print("\n✔️ Ingestion completed!")
    print("Total chunks stored:", global_id - 1)

if __name__ == "__main__":
    ingest_book()
