from langchain.prompts import PromptTemplate


class PromptFamily:

    @staticmethod
    def planner_prompt(query, json_summary):
        return f"""
        You are an expert clinical research assistant.

        You will receive:
        - A **user query** that asks for either *research* or *writing specific sections of a clinical trial protocol (M11 format)*
        - A **summary of a JSON file** that contains relevant trial design data


        user query: {query}
        JSON Summary: {json_summary}

        ---

        ## Research Mode

        1. UNDERSTAND THE REQUEST:
        - Carefully analyze the topic provided by the user
        - Identify the type of research needed
        - Identify if the user wants to research about sepecific topic

        If the user is requesting *general research help*, output ONE high-level section with:
        - `title`, `description`, and `research: true`

        ---

        ## Report Writing Mode


        1. UNDERSTAND THE REQUEST:
        - Carefully analyze the topic and outline provided by the user
        - Identify the type of research needed
        - Identify if the user wants to generate sepecific sections of report.
        - Identify if user wants to generate complete outline of the report

        2. GENERATE A COMPREHENSIVE REPORT STRUCTURE:
        - Create a detailed, hierarchical structure with:
            * Clear main sections
            * Relevant subsections under each main section

        3. FORMAT THE RESPONSE:
        - Present the report structure as a hierarchical outline with clear section numbering
        - Use descriptive titles for each section and subsection
        - Include brief descriptions of key sections when helpful
        - Provide the structure in a clean, easy-to-read format

        Return each top-level section as:
        - `title`: the full official section title from the M11 protocol (e.g., "Section 2 – Introduction")
        - `description`: a high-level overview of what the section contains
        - `research`: whether this section requires scientific research (True/False)
        - `subsections`: a list of subsections with titles, descriptions, and `research` flags

        Only include all the sections explicitly or implicitly requested in the user query. Do not return unrelated sections.
        Do not Generate sections from yourself.

        ---
        """


    @staticmethod
    def trial_design_prompt(json_data):
        return f"""
            You are an expert clinical trial design report writer.

            Summarize the following trial design data into a comprehensive and structured summary.

            # INSTRUCTIONS
            - This summary will be used to write the sections of a Trial Design Report based on the M11 protocol.
            - Ensure the summary includes all relevant details required for writing each report section.
            - As an experienced report writer, you should be aware of the data each M11 section requires; structure the summary accordingly.
            - Do not add any external or inferred information that is not present in the provided trial design data.
            - Provide only the summary—no commentary, headers, or additional text.

            Trial Design Data:
            {str(json_data)}
            """



    @staticmethod
    def query_rewrite_prompt():
        return PromptTemplate.from_template(
            """You are a retriever that rewrites queries for better document retrieval from a clinical database.
            You will be given the section title and description for which you have to retrive most relavent data.
            section title: {title}
            section description: {description}
            Rewrite the following user query to be more effective:\n\nUser Query: {query}"""
        )

    @staticmethod
    def generate_output_prompt(title, description, subsections, summary, context, total_words=200):
        return f"""You are provided with the following information:

        **Trial Design Summary:**  
        {summary}

        **Relevant Contextual Sources:**  
        {context}

        ---

        Write the following section of a clinical trial report using **only the provided context above**:

        **Section Title:** {title}  
        **Section Description:** {description}  
        **Subsections:** {subsections}  

        Your writing **must follow these rules**:

        - Must be at least {total_words} words long.
        - Use only the information available in the `context`. Do not introduce any other facts, quotes, or references.
        - Do not fabricate or hallucinate data, facts, quotes, or sources.
        - Do not cite any source that is not explicitly included in the `context`.
        - Cite external sources **only** if they are present in the context.
        - Cite using this format:
        - One author: (Jane Doe, 2023)
        - Multiple authors: (Smith et al., 2022)
        - No author: (NIH, 2023) or (ClinicalTrials.gov, 2022)

        **Markdown Formatting Rules:**

        - Format the response using Markdown: use headers, bullet points, and paragraphs.
        - Include a `### References` section at the end:
            - List only real sources from the context.
            - Use this format:
            - *Title of Article or Report*. https://url.com
            - Do **not** include:
                - User-uploaded documents
                - Summaries or notes
                - Placeholder links
                - Anything that is not in the context

        Be direct and professional. **Do not add any disclaimers, hallucinated references, or commentary outside the required content.**
        """
