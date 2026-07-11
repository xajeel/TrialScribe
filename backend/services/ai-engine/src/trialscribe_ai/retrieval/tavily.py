from langchain_tavily import TavilySearch
from trialscribe_ai.config.settings import MAX_RESULTS, ALLOWED_WEBSITES_FILE
import yaml

def load_allowed_domains(path):
    with open(path, "r") as f:
        domains = yaml.safe_load(f)

    allowed_domains = domains["allowed_domains"]
    return allowed_domains

web_search_tool = TavilySearch(
          max_results=MAX_RESULTS,
          topic="general",
          include_domains=load_allowed_domains(ALLOWED_WEBSITES_FILE),
        )


async def search_tool(query):
    return await web_search_tool.ainvoke({"query":query})
