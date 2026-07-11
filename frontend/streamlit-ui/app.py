import streamlit as st
import json
import os
import tempfile
from trialscribe_ai.models.schemas import AgentState
from trialscribe_ai.agents.researcher import ResearchAgent
from trialscribe_ai.retrieval.trial_processor import TrialDataProcessor
from trialscribe_ai.agents.planner import planner_agent
from trialscribe_ai.storage.evidence_db import EvidenceDatabase
from trialscribe_ai.core.llm import llm
from langgraph.graph import StateGraph, END
from trialscribe_ai.agents.writer import build_writer_agent

trial_processor = TrialDataProcessor()
database = EvidenceDatabase()

test_query = """ You are an expert medical writer specializing in clinical trials. 
You have a trial design represented by the data given. 
Your task is to write the M11 Clinical Trial Protocol Section 2, which includes the Study Rationale, Background, and Benefit/Risk Assessment. 
You must cite relevant sources, write concisely, and do not repeat what may be in other sections of the protocol."""

# Configure Streamlit page
st.set_page_config(
    page_title="TrialScribe",
    layout="wide"
)

def save_uploaded_file(uploaded_file, temp_dir):
    """Save uploaded file to temporary directory and return path"""
    if uploaded_file is not None:
        file_path = os.path.join(temp_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return file_path
    return None

def main():
    st.title("TrialScribe — Clinical Research Assistant")
    st.markdown("---")
    
    # Create temporary directory for file storage
    if 'temp_dir' not in st.session_state:
        st.session_state.temp_dir = tempfile.mkdtemp()
    
    # Sidebar for file uploads
    st.sidebar.header("File Uploads")
    
    # JSON file upload (required)
    st.sidebar.subheader("JSON Data File (Required)")
    json_file = st.sidebar.file_uploader(
        "Upload your JSON trial data file",
        type=['json'],
        help="This file contains the trial data to be processed"
    )
    
    # Supporting documents upload (optional)
    st.sidebar.subheader("Supporting Documents (Optional)")
    doc_files = st.sidebar.file_uploader(
        "Upload supporting documents",
        type=['pdf'],
        accept_multiple_files=True,
        help="Additional documents to enhance the research analysis"
    )
    
    # Main interface
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.header("Research Query")
        user_query = st.text_area(
            "Enter your research question:",
            value=test_query,
            height=100,
            help="Enter the specific research question you want to analyze"
        )

    with col2:
        st.header("Research Options")
        research = st.checkbox("External Research", value=False, help="Toggle the vaire option on or off")

    st.markdown("---")
    
    if st.button("Start Analysis", type="primary", use_container_width=True):
        # Validation
        if not json_file:
            st.error("Please upload a JSON file to proceed.")
            return
        
        if not user_query.strip():
            st.error("Please enter a research query.")
            return
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Save uploaded files
            status_text.text("Saving uploaded files...")
            progress_bar.progress(10)
            
            # Save JSON file
            print("Saving JSON file ...")
            json_path = save_uploaded_file(json_file, st.session_state.temp_dir)
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            
            json_fields = trial_processor.process_json(json_data)
            summary = database.add_json_data(json_fields)
            
            # Save document files if any
            print("Saving document files ...")
            doc_paths = []
            if doc_files:
                for doc_file in doc_files:
                    doc_path = save_uploaded_file(doc_file, st.session_state.temp_dir)
                    if doc_path:
                        doc_paths.append(doc_path)
            
            # Initialize classes
            status_text.text("Initializing processors...")
            progress_bar.progress(20)
            
            
            # ===================================== Process JSON data =====================================
            status_text.text("Processing JSON data...")
            progress_bar.progress(40)
            
            # with open(json_path, "r", encoding="utf-8") as f:
            #     json_data = json.load(f)
            
            # json_fields = trial_processor.process_json(json_data)
            # summary = database.add_json_data(json_fields)
            
            # ===================================== Add user documents if any =====================================
            if doc_paths:
                status_text.text("Processing supporting documents...")
                progress_bar.progress(50)
                database.add_user_documents(doc_paths)
            
            # ===================================== Execute research planning ==================================
            status_text.text("Executing research planning...")
            progress_bar.progress(70)
            
            research_agent = ResearchAgent(llm)

            def research_agent_node(state: AgentState):
                sections = state.sections
                research_agent.research_all_sections(sections)
                return {} 
            
            def research_condition_router(state: AgentState) -> str:
                if state.research:
                    return "research_node"
                else:
                    return "writer_node"

            
            graph = StateGraph(AgentState)

            graph.add_node( "planner_node", planner_agent)
            graph.add_node("research_node", research_agent_node)
            graph.add_node("writer_node", build_writer_agent)

            graph.add_conditional_edges(
                "planner_node",
                research_condition_router,
                {
                    "research_node": "research_node",
                    "writer_node": "writer_node",
                },
            )

            graph.add_edge("research_node", "writer_node")
            graph.add_edge("writer_node", END)

            graph.set_entry_point("planner_node")

            agent = graph.compile()


             # ===================================== Generate final output =====================================
            state = AgentState(
                query=user_query,
                sections=[],
                written_texts=[],
                summary=summary,
                research=research
            )
            
            status_text.text("Generating final analysis...")
            progress_bar.progress(90)
            final_state = agent.invoke(state)


            # ===================================== Display results =====================================
            if final_state["written_texts"]:
                st.markdown("---")
                st.header("Analysis Results")
                st.subheader("Final Analysis")
                
                for section_text in final_state["written_texts"]:
                    st.markdown(section_text)
                print("Completed ... ")
            else:
                st.warning("No content was generated. Please check your inputs.")

            
        except Exception as e:
            st.error(f"An error occurred during processing: {str(e)}")
            st.exception(e)
        
        finally:
            progress_bar.empty()
            status_text.empty()
    

if __name__ == "__main__":

    main()