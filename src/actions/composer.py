# ---- Sort and Assemble Final Report ----

def output_composer(sections, results):

    final_report = []
    all_references = []

    for i in range(len(sections)):
        result = results[i]
        final_report.append(f"## {result['title']}\n")
        final_report.append(result['content'])
        final_report.append("\n" + "-" * 80 + "\n")

        all_references.extend(result['references'])

    unique_references = list(dict.fromkeys(all_references))

    if unique_references:
        final_report.append("### References")
        for ref in unique_references:
            final_report.append(f"- {ref}")

    complete_report = "\n".join(final_report)

    return complete_report
