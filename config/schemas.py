from operator import add
from pydantic import BaseModel, Field
from typing import Annotated, List, Dict, Optional




class Query(BaseModel):
  pubmed: str
  tavily: str

class SearchQueries(BaseModel):
  queries: Query = Field(description="The queries to be answered")
  

# planner.py

class subsection(BaseModel):
    title: str
    description: str

class Section(BaseModel):
    title: str
    description: str
    subsections: Optional[List[subsection]] = None

class Sections(BaseModel):
    sections: List[Section] = Field(description="List of sections in the M11 protocol")

class AgentState(BaseModel):
    query: str
    sections: List[Section] = Field(description="List of sections in the research document")
    summary: str = Field(description="Summary of the trail design")
    written_texts: Annotated[List[str], add] = Field(description="List of written texts")
    research: bool = False


#  Researcher.py 

class Query(BaseModel):
  pubmed: str
  tavily: str

class SearchQueries(BaseModel):
  queries: Query = Field(description="The queries to be answered")