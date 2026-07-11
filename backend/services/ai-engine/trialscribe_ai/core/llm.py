from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from trialscribe_ai.config import settings  # noqa: F401 — triggers load_dotenv() before os.getenv below
import os

api = os.getenv("OPENAI_API_KEY")

embedding_model = OpenAIEmbeddings(model="text-embedding-3-large", api_key=api)
llm = ChatOpenAI(
    model="gpt-4.1",
    temperature=0
)
