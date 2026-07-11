# from retriever import Retriever
from config.schemas import AgentState
from src.retriever import Retriever
from utils.util import llm
from utils.prompt import PromptFamily
from langgraph.graph import StateGraph, END
import os

K_value = int(os.getenv("K_value", "10"))
NUM_WORDS = int(os.getenv("NUM_WORDS", "500"))
retriever = Retriever()

def writer_agent(state: AgentState, section_data, model=llm):
    print("Section Writing ...")
    section = section_data.model_dump()
    summary = state.summary
    user_query = state.query
    section_title = section.get("title", "No title")
    section_description = section.get("description", "No description")
    subsections = section.get("subsections", [])

    retrive_data = retriever.retrieve(
        user_query, section_title, section_description, k=K_value)

    prompt = PromptFamily.generate_output_prompt(
        title=section_title,
        description=section_description,
        subsections=subsections,
        summary=summary,
        context=retrive_data,
        total_words=NUM_WORDS
    )

    response = model.invoke([{"role": "user", "content": prompt}])

    return {
        "written_texts": [response.content]
    }


def build_writer_agent(state: AgentState):

    graph = StateGraph(AgentState)
    sections = state.sections

    for index, section in enumerate(sections):
        node = f"node_{index}"

        def section_writer(state: AgentState, section=section):
            return writer_agent(state, section)

        graph.add_node(node, section_writer)
        graph.set_entry_point(node)
        graph.add_edge(node, END)

    return graph.compile()
