from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from trialscribe_ai.prompts.templates import PromptFamily
from typing import List, Dict
import os

from trialscribe_ai.core.llm import embedding_model, llm

class EvidenceDatabase:
    def __init__(self, user_index_path: str = "userdata_index", evidence_index_path: str = "evidence_index"):
        self.embedding_model = embedding_model
        self.user_index_path = user_index_path
        self.evidence_index_path = evidence_index_path

        self.userdata_db = None
        self.evidence_db = None

        self.load_indexes()


    def load_indexes(self):
        """Load both FAISS indexes from disk"""
        if os.path.exists(self.user_index_path):
            try:
                self.userdata_db = FAISS.load_local(self.user_index_path, self.embedding_model, allow_dangerous_deserialization=True)
            except Exception:
                self.userdata_db = None

        if os.path.exists(self.evidence_index_path):
            try:
                self.evidence_db = FAISS.load_local(self.evidence_index_path, self.embedding_model, allow_dangerous_deserialization=True)
            except Exception:
                self.evidence_db = None


    def save_user_index(self):
        if self.userdata_db is not None:
            self.userdata_db.save_local(self.user_index_path)

    def save_evidence_index(self):
        if self.evidence_db is not None:
            self.evidence_db.save_local(self.evidence_index_path)


    def _init_db_if_needed(self, documents: List[Document], db_type: str):
        if db_type == "user":
            if self.userdata_db is None:
                self.userdata_db = FAISS.from_documents(documents, self.embedding_model)
            else:
                self.userdata_db.add_documents(documents)
            self.save_user_index()

        elif db_type == "evidence":
            if self.evidence_db is None:
                self.evidence_db = FAISS.from_documents(documents, self.embedding_model)
            else:
                self.evidence_db.add_documents(documents)
            self.save_evidence_index()


    def _split_documents(self, documents, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Split documents into smaller chunks
        """
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        return text_splitter.split_documents(documents)

    def add_pubmed_data(self, items: List[Dict], section=None):
        documents = []
        valid_docs = 0
        
        for item in items:
            content = item.get("content") or item.get("abstract") or item.get("summary", "")
            if not content or content.strip() == "":
                continue
            content = str(content).strip()
            if len(content) < 10:
                continue
                
            metadata = {
                "title": item.get("title", "Untitled"),
                "link": item.get("link", ""),
                "source": "pubmed",
                "pmid": item.get("pmid", ""),
                "authors": item.get("authors", ""),
                "section": section
            }
            
            documents.append(Document(page_content=content, metadata=metadata))
            valid_docs += 1
        
        if documents:
            documents = self._split_documents(documents=documents)
            self._init_db_if_needed(documents, db_type="evidence")
            print(f"Added {valid_docs} PubMed documents to vector DB.")
        else:
            print("No valid PubMed documents found to add.")

    def add_user_documents(self, file_paths: List[str]):
        all_docs = []

        for file_path in file_paths:
            loader = PyPDFLoader(file_path)
            docs = loader.load()
            for doc in docs:
                doc.metadata["title"] = os.path.basename(file_path)
                doc.metadata["source"] = "user"
            all_docs.extend(docs)

        all_docs = self._split_documents(documents=all_docs)
        self._init_db_if_needed(all_docs, db_type="user")
        print(f"Added {len(all_docs)} documents to FIASS vector DB.")

# ========== JSON Data Handling ==========

    def add_json_data(self, json_data: Dict):
        json_str = str(json_data)
        # prompt = ChatPromptTemplate.from_messages([
        #     ("system", "You are a helpful assistant that summarizes JSON data for storage in a vector database."),
        #     ("human", "Summarize the following JSON data:\n{json_str}")
        # ])

        prompt = PromptFamily.trial_design_prompt(json_str)

        summary = llm.invoke([{"role": "user", "content": prompt}])
        metadata = {
            "source": "json_upload",
            "title": json_data.get("title", "JSON Data"),
        }
        doc = Document(page_content=summary.content, metadata=metadata)
        self._init_db_if_needed([doc], db_type="user")

        return summary.content
    
# ========== Search Data Handling ==========

    def add_search_data(self, items: List[Dict], section=None):
        documents = []
        valid_docs = 0
        
        for item in items:
            content = item.get("content") or item.get("abstract") or item.get("summary", "")
            if not content or content.strip() == "":
                continue
            content = str(content).strip()
            if len(content) < 10:
                continue
                
            metadata = {
                "title": item.get("title", "Untitled"),
                "link": item.get("url", ""),
                "source": "search",
                "section": section
            }
            
            documents.append(Document(page_content=content, metadata=metadata))
            valid_docs += 1
        
        if documents:
            documents = self._split_documents(documents=documents)
            self._init_db_if_needed(documents, db_type="evidence")
            print(f"Added {valid_docs} documents to vector DB.")
        else:
            print("No valid documents found to add.")

    def search_user_data(self, query: str, k: int = 5):
        if self.userdata_db is None:
            return []
        return self.userdata_db.similarity_search_with_score(query, k=k)

    def search_evidence_data(self, query: str, k: int = 5):
        if self.evidence_db is None:
            return []
        return self.evidence_db.similarity_search_with_score(query, k=k)