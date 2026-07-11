from trialscribe_ai.models.schemas import AgentState
from trialscribe_ai.retrieval.retriever import Retriever
from trialscribe_ai.core.llm import llm
from trialscribe_ai.prompts.templates import PromptFamily
from trialscribe_ai.config.settings import K_VALUE, NUM_WORDS
from langgraph.graph import StateGraph, END

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
        user_query, section_title, section_description, k=K_VALUE)

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
