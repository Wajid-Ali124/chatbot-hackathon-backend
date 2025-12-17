from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents import Agent, Runner, OpenAIChatCompletionsModel, AsyncOpenAI
from agents import set_tracing_disabled, function_tool
import os
from dotenv import load_dotenv
import cohere
from qdrant_client import QdrantClient

load_dotenv()
set_tracing_disabled(disabled=True)

app = FastAPI()

# CORS - Allow your frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize clients
gemini_api_key = os.getenv("GEMINI_API_KEY")
provider = AsyncOpenAI(
    api_key=gemini_api_key,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
)

model = OpenAIChatCompletionsModel(
    model="gemini-2.5-flash-lite",
    openai_client=provider
)

cohere_client = cohere.Client(os.getenv("COHERE_API_KEY"))
qdrant = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY")
)

def get_embedding(text):
    response = cohere_client.embed(
        model="embed-english-v3.0",
        input_type="search_query",
        texts=[text],
    )
    return response.embeddings[0]

@function_tool
def retrieve(query):
    """Retrieve relevant content from the knowledge base."""
    embedding = get_embedding(query)
    result = qdrant.query_points(
        collection_name="ai-powered-book",
        query=embedding,
        limit=5
    )
    return [point.payload["text"] for point in result.points]

agent = Agent(
    name="Assistant",
    instructions="""
You are an AI tutor for the AI and ML Book.
To answer the user question, first call the tool `retrieve` with the user query.
Use ONLY the returned content from `retrieve` to answer.
If the answer is not in the retrieved content, say "Reached Free tier usages".
""",
    model=model,
    tools=[retrieve]
)

class QueryRequest(BaseModel):
    question: str

class QueryResponse(BaseModel):
    answer: str


@app.post("/api/chat")
async def chat(request: QueryRequest):
    try:
        result = await Runner.run(agent, input=request.question)
        return QueryResponse(answer=result.final_output)
    except Exception as e:
        # Print full error to console
        import traceback
        print("ERROR:", str(e))
        print("TRACEBACK:", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy"}