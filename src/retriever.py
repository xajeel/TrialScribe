from src.database import EvidenceDatabase
from utils.util import llm
from utils.prompt import PromptFamily

from dotenv import load_dotenv
import os

class Retriever:
    def __init__(self):
        self.database = EvidenceDatabase()
        self.query_prompt = PromptFamily.query_rewrite_prompt()
        self.chain = self.query_prompt | llm

    def retrieve(self, user_query: str, section_title: str, section_description:str, k: int) -> list:
        """Retrieve relevant documents based on the user query."""
        print("Fetching Data ...")
        formulated_query = self._query_formulator(user_query, section_title, section_description)
        results = self._search_database(formulated_query, k=k)
        return results

    def _query_formulator(self, user_query: str, section_title: str, section_description:str) -> str:
        """Formulate a query for the retriever using the LLM."""
        response = self.chain.invoke({"query": user_query, "title": section_title, "description": section_description})
        return response.content if hasattr(response, "content") else str(response)
    
    def _search_database(self, formulated_query: str, k: int) -> list:
        """Search both user and evidence databases, prioritize user data."""
        user_results = self.database.search_user_data(formulated_query, k=k)
        evidence_results = self.database.search_evidence_data(formulated_query, k=k)

        combined = []

        # Prioritize user data by appending it first
        for doc, score in user_results:
            combined.append({
                "title": doc.metadata.get("title", "No Title"),
                "link": doc.metadata.get("link", "No link"),
                "content": doc.page_content.strip(),
                "score": score,
                "source": "user"
            })

        for doc, score in evidence_results:
            combined.append({
                "title": doc.metadata.get("title", "No Title"),
                "link": doc.metadata.get("link", "No link"),
                "content": doc.page_content.strip(),
                "score": score,
                "source": "evidence"
            })

        # Optional: sort combined results by score (lowest = most relevant)
        combined.sort(key=lambda x: x["score"])

        # Optional: limit total returned results
        return combined

