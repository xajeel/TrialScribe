from langchain_tavily import TavilySearch
import yaml
import os

MAX_RESULTS = int(os.getenv("MAX_RESULTS", "5"))

def init_web_searc_tool(path):
    with open(path, "r") as f:
        domains = yaml.safe_load(f)

    allowed_domains = domains["allowed_domains"]
    return allowed_domains

web_search_tool = TavilySearch(
          max_results=MAX_RESULTS,
          topic="general",
          include_domains=init_web_searc_tool("config/allowed_websites.yml"),
        )


async def search_tool(query):
    return await web_search_tool.ainvoke({"query":query})
