import os
import xml.etree.ElementTree as ET
import requests

class PubMedAgent:

    def __init__(self, query_domains=None):
        self.api_key = self._retrieve_api_key()

    def _retrieve_api_key(self):
        api_key = os.getenv("NCBI_API_KEY")
        if not api_key:
            raise Exception(
                "NCBI API key not found. Set NCBI_API_KEY in your .env file."
            )
        return api_key

    def search(self, query ,max_results=1):
        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pmc",
            "term": f"{query}",
            "retmax": max_results,
            "usehistory": "y",
            "api_key": self.api_key,
            "retmode": "json",
            "sort": "relevance"
        }
        response = requests.get(base_url, params=params)

        if response.status_code != 200:
            raise Exception(
                f"Failed to retrieve data: {response.status_code} - {response.text}"
            )

        results = response.json()
        ids = results["esearchresult"]["idlist"]

        search_response = []
        for article_id in ids:
            xml_content = self.fetch([article_id])
            if self.has_body_content(xml_content):
                article_data = self.parse_xml(xml_content)
                if article_data:
                    search_response.append(
                        {
                            "link": f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{article_id}/",
                            "title": f"{article_data['title']}",
                            "authors": article_data["authors"],
                            "content": f"n{article_data['abstract']}\n\n{article_data['body']}..."
                        }
                    )

            if len(search_response) >= max_results:
                break

        return search_response

    def fetch(self, ids):

        base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            "db": "pmc",
            "id": ",".join(ids),
            "retmode": "xml",
            "api_key": self.api_key,
        }
        response = requests.get(base_url, params=params)

        if response.status_code != 200:
            raise Exception(
                f"Failed to retrieve data: {response.status_code} - {response.text}"
            )

        return response.text

    def has_body_content(self, xml_content):
        root = ET.fromstring(xml_content)
        ns = {
            "mml": "http://www.w3.org/1998/Math/MathML",
            "xlink": "http://www.w3.org/1999/xlink",
        }
        article = root.find("article", ns)
        if article is None:
            return False

        body_elem = article.find(".//body", namespaces=ns)
        if body_elem is not None:
            return True
        else:
            for sec in article.findall(".//sec", namespaces=ns):
                for p in sec.findall(".//p", namespaces=ns):
                    if p.text:
                        return True
        return False

    def parse_xml(self, xml_content):
        root = ET.fromstring(xml_content)
        ns = {
            "mml": "http://www.w3.org/1998/Math/MathML",
            "xlink": "http://www.w3.org/1999/xlink",
        }

        article = root.find("article", ns)
        if article is None:
            return None

        title = article.findtext(
            ".//title-group/article-title", default="", namespaces=ns
        )

        abstract = article.find(".//abstract", namespaces=ns)
        abstract_text = (
            "".join(abstract.itertext()).strip() if abstract is not None else ""
        )

        authors = []
        contribs = article.findall(".//contrib-group/contrib[@contrib-type='author']", namespaces=ns)
        for contrib in contribs:
            name_elem = contrib.find("name", namespaces=ns)
            if name_elem is not None:
                surname = name_elem.findtext("surname", default="", namespaces=ns)
                given_names = name_elem.findtext("given-names", default="", namespaces=ns)
                full_name = f"{given_names} {surname}".strip()
                if full_name:
                    authors.append(full_name)


        body = []
        body_elem = article.find(".//body", namespaces=ns)
        if body_elem is not None:
            for p in body_elem.findall(".//p", namespaces=ns):
                if p.text:
                    body.append(p.text.strip())
        else:
            for sec in article.findall(".//sec", namespaces=ns):
                for p in sec.findall(".//p", namespaces=ns):
                    if p.text:
                        body.append(p.text.strip())

        return {"title": title, "abstract": abstract_text, "body": "\n".join(body), "authors": authors}