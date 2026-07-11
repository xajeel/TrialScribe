from config.schemas import SearchQueries
from utils.retrievers.pubmed import PubMedAgent
from src.database import EvidenceDatabase
from utils.retrievers.tavilytool import search_tool
from utils.util import llm
import os

MAX_RESULTS = int(os.getenv("MAX_RESULTS", "5"))
os.environ["TAVILY_API_KEY"] = os.getenv("TAVILY_API_KEY")

class ResearchAgent:
    def __init__(self, llm):
        self.pubmed_tool = PubMedAgent()
        self.database = EvidenceDatabase()
        self.llm = llm
    
    def _generate_query(self, section_title: str, description: str) -> str:
        prompt = f""" You are a search queries generator specialist. Create searche quries using the instructions provided by your user.

                Instructions:
                1. Create reseach quries for the pubmed tool and tavily search
                2. First try exact keywords and then Try alternative keywords if no results found (broader terms, synonyms)
                "Section: {section_title}\n Description: {description}"
                """
        
        model = llm.with_structured_output(SearchQueries)
        query = model.invoke(prompt)
        return query.model_dump()
    
    async def research_section(self, section_title: str, description: str = ""):
        query = self._generate_query(section_title, description)

        print(query)
        print(type(query))
        # query = json.loads(query)
        
        print("PubMed tool")
        pubmed_results = self.pubmed_tool.search(query['queries'].get("pubmed"), max_results=MAX_RESULTS)
        if pubmed_results:
          self.database.add_pubmed_data(pubmed_results, section=section_title)
        
        print("Tavily tool")
        tavily_results = await search_tool(query['queries'].get("tavily"))
        if tavily_results:
          self.database.add_search_data(tavily_results["results"], section=section_title)

    async def research_all_sections(self, sections: list):
        print("Researcher ... ")
        for section in sections:
            section_title = section.title
            description = section.description
            await self.research_section(section_title, description)