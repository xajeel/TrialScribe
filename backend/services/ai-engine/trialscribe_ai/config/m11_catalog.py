"""Versioned ICH M11 top-level protocol section catalog."""

from dataclasses import dataclass

M11_CATALOG_VERSION = "ICH_M11_STEP_4_2025_11_19"


@dataclass(frozen=True, slots=True)
class M11SectionDefinition:
    """One immutable top-level section in the supported M11 template."""

    number: str
    title: str
    position: int


M11_SECTION_CATALOG = (
    M11SectionDefinition("1", "PROTOCOL SUMMARY", 1),
    M11SectionDefinition("2", "INTRODUCTION", 2),
    M11SectionDefinition(
        "3",
        "TRIAL OBJECTIVES AND ASSOCIATED ESTIMANDS",
        3,
    ),
    M11SectionDefinition("4", "TRIAL DESIGN", 4),
    M11SectionDefinition("5", "TRIAL POPULATION", 5),
    M11SectionDefinition(
        "6",
        "TRIAL INTERVENTION AND CONCOMITANT THERAPY",
        6,
    ),
    M11SectionDefinition(
        "7",
        "PARTICIPANT DISCONTINUATION OF TRIAL INTERVENTION AND "
        "DISCONTINUATION OR WITHDRAWAL FROM TRIAL",
        7,
    ),
    M11SectionDefinition("8", "TRIAL ASSESSMENTS AND PROCEDURES", 8),
    M11SectionDefinition(
        "9",
        "ADVERSE EVENTS, SERIOUS ADVERSE EVENTS, PRODUCT COMPLAINTS, "
        "PREGNANCY AND POSTPARTUM INFORMATION, AND SPECIAL SAFETY SITUATIONS",
        9,
    ),
    M11SectionDefinition("10", "STATISTICAL CONSIDERATIONS", 10),
    M11SectionDefinition(
        "11",
        "TRIAL OVERSIGHT AND OTHER GENERAL CONSIDERATIONS",
        11,
    ),
    M11SectionDefinition("12", "APPENDIX: SUPPORTING DETAILS", 12),
    M11SectionDefinition(
        "13",
        "APPENDIX: GLOSSARY OF TERMS AND ABBREVIATIONS",
        13,
    ),
    M11SectionDefinition("14", "APPENDIX: REFERENCES", 14),
)
