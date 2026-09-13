"""Decide which web addresses may be stored as conversation evidence."""

import hashlib
from datetime import date
from urllib.parse import urlparse, urlunparse

from trialscribe_worker.utils.constant import MAX_SOURCE_IDENTITY_LENGTH

DEFAULT_ALLOWED_WEB_DOMAINS: frozenset[str] = frozenset(
    {
        "aapc.com",
        "academic.oup.com",
        "ahajournals.org",
        "ajnr.org",
        "aruplab.com",
        "ashpublications.org",
        "auth.gr",
        "bdbiosciences.com",
        "becarispublishing.com",
        "bio-techne.com",
        "blueprintgenetics.com",
        "bridgespan.org",
        "bvhealthsystem.org",
        "cancer.iu.edu",
        "cancer.org",
        "cardionavigator.com",
        "cdc.gov",
        "cdisc.org",
        "cedars-sinai.org",
        "clevelandclinic.org",
        "clinicalepigeneticsjournal.biomedcentral.com",
        "clinicaltrials.gov",
        "cms.gov",
        "coas.iqvia.com",
        "computationalpathologygroup.eu",
        "cyto.purdue.edu",
        "dermnetnz.org",
        "dlmp.uw.edu",
        "elitecardiovascular.com",
        "emedicine.medscape.com",
        "eprovide.mapi-trust.org",
        "eurofins.com",
        "facit.org",
        "fda.gov",
        "fulgentgenetics.com",
        "hcahealthcare.com",
        "health.harvard.edu",
        "healthy.kaiserpermanente.org",
        "hhs.gov",
        "hmpglobalevents.com",
        "hologic.com",
        "jamanetwork.com",
        "jnm.snmjournals.org",
        "journals.plos.org",
        "kdqol-complete.org",
        "labcorp.com",
        "lawrencegeneral.org",
        "link.springer.com",
        "loinc.org",
        "massgeneral.org",
        "mayoclinic.org",
        "mda.gesis.org",
        "mdanderson.org",
        "medlineplus.gov",
        "mms.mckesson.com",
        "mountsinai.org",
        "mskcc.org",
        "nature.com",
        "ncbi.nlm.nih.gov",
        "neogenomics.com",
        "nhs.uk",
        "nih.gov",
        "nursing.vanderbilt.edu",
        "oml.eular.org",
        "onlinelibrary.wiley.com",
        "ou.edu",
        "pearsonclinical.com.au",
        "pockethealth.com",
        "ppd.com",
        "qualitymetric.com",
        "questdiagnostics.com",
        "rand.org",
        "rbm.q2labsolutions.com",
        "rch.org.au",
        "redcross.org",
        "redwoodtoxicology.com",
        "research.jefferson.edu",
        "researchgate.net",
        "rheumatology.org",
        "scielo.br",
        "sciencedirect.com",
        "site.thoracic.org",
        "sjra.com",
        "snomed.org",
        "sralab.org",
        "stanfordlab.com",
        "testmenu.com",
        "thermofisher.com",
        "uchicago.edu",
        "umich.edu",
        "unityhealth.to",
        "upenn.edu",
        "usf.edu",
        "uwcorr.washington.edu",
        "verywellhealth.com",
        "who.int",
        "wpspublish.com",
    }
)


def canonical_url(raw: str) -> str | None:
    """Return a comparable https URL, or nothing when the value is not a page."""

    stripped = raw.strip()
    if not stripped:
        return None
    parsed = urlparse(stripped)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse(
        (parsed.scheme, host, path, "", parsed.query, "")
    )


def source_identity_for(url: str) -> str:
    """Return the evidence identity for one canonical page address."""

    if len(url) <= MAX_SOURCE_IDENTITY_LENGTH:
        return url
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def host_allowed(
    url: str,
    domains: frozenset[str] | None = None,
) -> bool:
    """Return whether this page's host is on the trusted website list."""

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    allowed = DEFAULT_ALLOWED_WEB_DOMAINS if domains is None else domains
    for domain in allowed:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def format_web_passage(
    *,
    title: str,
    url: str,
    published_on: date | None,
    retrieved_on: date,
    body: str,
) -> str:
    """Return passage text with title, address, dates, then the quoted body."""

    published = published_on.isoformat() if published_on is not None else "unknown"
    return (
        f"Title: {title}\n"
        f"URL: {url}\n"
        f"Date: {published}\n"
        f"Retrieved: {retrieved_on.isoformat()}\n"
        f"\n"
        f"{body}"
    )
