#  Embeddign Functions

from langchain_openai import OpenAIEmbeddings
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import os
load_dotenv()
api = os.getenv("OPENAI_API_KEY")


# Open AI Models
embedding_model = OpenAIEmbeddings(model="text-embedding-3-large", api_key=api)
llm = ChatOpenAI(
    model="gpt-4.1",
    temperature=0
)

# 