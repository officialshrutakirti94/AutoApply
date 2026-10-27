"""Resume -> structured profile.

Two parsers always run:

* a deterministic heuristic parser (no cost, no network, works with no API key)
* the LLM parser, when a provider is configured

The LLM output wins where it is present, but the heuristic result is never thrown
away: it is the fallback, and it is what makes every extracted field carry a
confidence the UI can highlight. Nothing here is final until the user confirms.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.agents import llm
from app.core.logging import get_logger
from app.core.prompts import RESUME_PARSE_SYSTEM, build_resume_parse_user

log = get_logger("resume_parse")

HIGH, MEDIUM, LOW = "high", "medium", "low"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+\d{1,3}[\s-]?)?(?:\d{10}|\d{5}[\s-]\d{5}|\d{3}[\s-]\d{3}[\s-]\d{4})(?!\d)"
)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-%.]+", re.IGNORECASE)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w\-%.]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[\w\-.]+(?:\.[a-z]{2,})(?:/[\w\-./?%&=+#]*)?", re.IGNORECASE)
YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)", re.IGNORECASE)
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
RANGE_RE = re.compile(
    rf"(?:{_MONTH}\s*)?((?:19|20)\d{{2}})\s*(?:-|–|—|to|until)\s*"
    rf"((?:{_MONTH}\s*)?(?:19|20)\d{{2}}|present|current|now|till\s+date)",
    re.IGNORECASE,
)
SECTION_RE = re.compile(r"^[A-Z][A-Z &/,\-]{2,38}:?$")
COMPANY_RE = re.compile(r"(?:\bat\b|\@)\s+([A-Z][A-Za-z0-9&.\- ]{1,38})")
BULLET_PREFIX = re.compile(r"^[\-•*·▪◦‣o]\s*")

TITLE_WORDS = (
    "engineer|developer|architect|analyst|consultant|manager|lead|designer|scientist|"
    "administrator|specialist|intern|associate|director|head|founder|programmer|"
    "devops|sre|qa|tester|recruiter|accountant|marketer|strategist"
)
TITLE_RE = re.compile(rf"\b(?:{TITLE_WORDS})\b", re.IGNORECASE)
DEGREE_RE = re.compile(
    r"\b(b\.?tech|m\.?tech|b\.?e\.?|m\.?e\.?|b\.?sc|m\.?sc|bca|mca|mba|bba|ph\.?d|"
    r"bachelor|master|diploma|b\.?com|m\.?com|b\.?a\.?|m\.?a\.?)\b",
    re.IGNORECASE,
)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

KNOWN_CITIES = {
    "bengaluru", "bangalore", "mumbai", "pune", "delhi", "new delhi", "noida", "gurgaon",
    "gurugram", "hyderabad", "chennai", "kolkata", "ahmedabad", "jaipur", "indore",
    "kochi", "coimbatore", "chandigarh", "lucknow", "nagpur", "surat", "bhopal",
    "london", "berlin", "dublin", "amsterdam", "toronto", "vancouver", "new york",
    "san francisco", "seattle", "austin", "boston", "singapore", "dubai", "sydney",
}

SKILL_VOCAB: tuple[str, ...] = (
    "python", "java", "javascript", "typescript", "react", "next.js", "node.js", "express",
    "django", "flask", "fastapi", "spring boot", "spring", "golang", "go", "rust", "c++",
    "c#", ".net", "php", "ruby", "rails", "kotlin", "swift", "sql", "postgresql", "mysql",
    "mongodb", "redis", "elasticsearch", "kafka", "rabbitmq", "docker", "kubernetes",
    "terraform", "ansible", "aws", "gcp", "azure", "linux", "git", "graphql", "rest api",
    "microservices", "ci/cd", "jenkins", "github actions", "airflow", "spark", "hadoop",
    "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "machine learning",
    "deep learning", "nlp", "computer vision", "data analysis", "tableau", "power bi",
    "excel", "figma", "adobe xd", "ui/ux", "product management", "agile", "scrum", "jira",
    "seo", "google analytics", "salesforce", "sap", "tally", "financial modeling",
    "accounting", "recruitment", "operations", "customer success", "content writing",
    "copywriting", "social media marketing", "html", "css", "tailwind", "redux",
)

SKILL_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Backend Engineer", ("python", "django", "flask", "fastapi", "node.js", "express", "java", "spring", "golang", "microservices", "rest api")),
    ("Frontend Engineer", ("react", "next.js", "javascript", "typescript", "html", "css", "tailwind", "redux")),
    ("Full Stack Engineer", ("react", "node.js", "typescript")),
    ("Data Analyst", ("sql", "pandas", "tableau", "power bi", "excel", "data analysis")),
    ("Data Engineer", ("airflow", "spark", "kafka", "hadoop", "postgresql")),
    ("ML Engineer", ("machine learning", "pytorch", "tensorflow", "scikit-learn", "deep learning", "nlp")),
    ("DevOps Engineer", ("docker", "kubernetes", "terraform", "aws", "gcp", "ci/cd", "jenkins")),
    ("Product Designer", ("figma", "adobe xd", "ui/ux")),
    ("Product Manager", ("product management", "jira", "agile", "scrum")),
    ("Marketing Specialist", ("seo", "content writing", "copywriting", "social media marketing", "google analytics")),
)

ROLE_DOMAINS: dict[str, str] = {
    "Backend Engineer": "Software",
    "Frontend Engineer": "Software",
    "Full Stack Engineer": "Software",
    "DevOps Engineer": "Infrastructure",
    "ML Engineer": "Data & AI",
    "Data Analyst": "Data & AI",
    "Data Engineer": "Data & AI",
    "Product Designer": "Design",
    "Product Manager": "Product",
    "Marketing Specialist": "Marketing & Growth",
}


class EducationItem(BaseModel):
    degree: str | None = None
    institution: str | None = None
    year: str | None = None


class ParsedResume(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    portfolio_url: str | None = None
    summary: str | None = None
    skills: list[str] = Field(default_factory=list)
    years_of_experience: float | None = None
    current_title: str | None = None
    current_company: str | None = None
    education: list[EducationItem] = Field(default_factory=list)
    suggested_roles: list[str] = Field(default_factory=list)
    suggested_domains: list[str] = Field(default_factory=list)
    confidence: dict[str, str] = Field(default_factory=dict)
    source: str = "heuristic"


# ------------------------------------------------------------------ heuristics


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        if SECTION_RE.match(line) and len(line.split()) <= 5:
            current = line.rstrip(":").strip().lower()
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def _section_text(sections: dict[str, list[str]], *names: str) -> str | None:
    for name in names:
        for key, values in sections.items():
            if name in key:
                joined = "\n".join(values).strip()
                if joined:
                    return joined
    return None


def _clean_url(match: str) -> str:
    url = match.strip().rstrip(".,);")
    if not url.lower().startswith("http"):
        url = "https://" + url
    return url


def _find_name(lines: list[str]) -> tuple[str | None, str]:
    blocked = {
        "resume", "curriculum vitae", "cv", "profile", "contact", "personal details",
        "summary", "objective", "experience", "education", "skills",
    }
    for index, line in enumerate(lines[:12]):
        candidate = BULLET_PREFIX.sub("", line).strip()
        if not candidate or candidate.lower().strip(":") in blocked:
            continue
        if any(char in candidate for char in "@|/\\0123456789"):
            continue
        if TITLE_RE.search(candidate) or DEGREE_RE.search(candidate):
            continue
        words = candidate.split()
        if not 2 <= len(words) <= 4 or len(candidate) > 45:
            continue
        if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", word) for word in words):
            continue
        formatted = " ".join(word.capitalize() if word.isupper() or word.islower() else word for word in words)
        return formatted, HIGH if index <= 2 else MEDIUM
    return None, LOW


def _find_location(text: str, lines: list[str]) -> str | None:
    labelled = re.search(r"(?:location|address|based in|city)\s*[:\-]\s*([A-Za-z .'\-]{2,40})", text, re.IGNORECASE)
    if labelled:
        return labelled.group(1).strip().rstrip(",")
    for line in lines[:20]:
        lower = line.lower()
        if any(city in lower for city in KNOWN_CITIES):
            fragment = re.split(r"[|•·,]", line)[0].strip()
            if 2 <= len(fragment) <= 60:
                return fragment
    return None


def _find_years_of_experience(text: str) -> tuple[float | None, str]:
    explicit = [float(match) for match in YEARS_RE.findall(text) if float(match) <= 45]
    if explicit:
        return max(explicit), MEDIUM

    now_year = datetime.now().year
    months = 0
    for start_raw, end_raw in RANGE_RE.findall(text):
        start_value = int(start_raw)
        normalized_end = end_raw.strip().lower()
        if normalized_end.startswith(("present", "current", "now", "till")):
            end_value = now_year
        else:
            digits = re.search(r"(?:19|20)\d{2}", end_raw)
            end_value = int(digits.group(0)) if digits else now_year
        if 1990 <= start_value <= now_year and end_value >= start_value:
            months += (end_value - start_value) * 12

    if months:
        return round(months / 12, 1), LOW
    return None, LOW


def _find_title(lines: list[str]) -> str | None:
    for line in lines[:25]:
        cleaned = BULLET_PREFIX.sub("", line).strip()
        if len(cleaned) > 70 or "@" in cleaned:
            continue
        if TITLE_RE.search(cleaned):
            return cleaned
    return None


def _find_company(text: str) -> str | None:
    labelled = re.search(r"(?:company|organi[sz]ation|employer)\s*[:\-]\s*([A-Za-z0-9&.\- ]{2,40})", text, re.IGNORECASE)
    if labelled:
        return labelled.group(1).strip()
    match = COMPANY_RE.search(text)
    if match:
        candidate = re.split(r"[|•·,.\n]", match.group(1))[0].strip()
        if 1 < len(candidate) <= 40:
            return candidate
    return None


def _find_education(sections: dict[str, list[str]], lines: list[str]) -> list[EducationItem]:
    block = _section_text(sections, "education", "academic", "qualification")
    source = block.splitlines() if block else lines
    items: list[EducationItem] = []
    for line in source:
        if not DEGREE_RE.search(line):
            continue
        year_match = YEAR_RE.search(line)
        parts = [part.strip() for part in re.split(r"[,|•·]", line) if part.strip()]
        degree = next((part for part in parts if DEGREE_RE.search(part)), line[:120])
        institution = next(
            (part for part in parts if re.search(r"(college|university|institute|school|academy)", part, re.IGNORECASE)),
            None,
        )
        items.append(
            EducationItem(
                degree=degree[:160],
                institution=institution[:160] if institution else None,
                year=year_match.group(0) if year_match else None,
            )
        )
        if len(items) >= 4:
            break
    return items


def _find_skills(text: str, sections: dict[str, list[str]]) -> tuple[list[str], str]:
    found: list[str] = []
    confidence = LOW

    block = _section_text(sections, "skill", "technolog", "technical", "tools", "expertise")
    if block:
        confidence = HIGH
        for token in re.split(r"[,|•·\n/]", block):
            token = BULLET_PREFIX.sub("", token).strip(" .;:")
            if 1 < len(token) <= 40 and len(token.split()) <= 4:
                found.append(token)

    lowered = text.lower()
    for skill in SKILL_VOCAB:
        if re.search(rf"(?<![\w.]){re.escape(skill)}(?![\w.])", lowered):
            found.append(skill)
            confidence = max(confidence, MEDIUM, key=[LOW, MEDIUM, HIGH].index)

    deduped: list[str] = []
    seen: set[str] = set()
    for skill in found:
        key = skill.lower().strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(skill.strip())
    return deduped[:40], confidence


def _derive_roles(skills: list[str], current_title: str | None) -> tuple[list[str], list[str]]:
    lowered = {skill.lower() for skill in skills}
    roles: list[str] = []
    for role, triggers in SKILL_ROLES:
        hits = sum(1 for trigger in triggers if trigger in lowered)
        if hits >= (2 if len(triggers) > 3 else 1):
            roles.append(role)
    if current_title and len(current_title) <= 60:
        roles.insert(0, current_title)
    if not roles:
        roles = ["Software Engineer"]
    deduped: list[str] = []
    for role in roles:
        if role.lower() not in {existing.lower() for existing in deduped}:
            deduped.append(role)
    domains = sorted({ROLE_DOMAINS[role] for role in deduped if role in ROLE_DOMAINS}) or ["Software"]
    return deduped[:6], domains


def heuristic_parse(text: str) -> ParsedResume:
    lines = _lines(text)
    sections = _sections(lines)

    name, name_confidence = _find_name(lines)
    location = _find_location(text, lines)
    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)
    linkedin_match = LINKEDIN_RE.search(text)
    github_match = GITHUB_RE.search(text)
    other_urls = [match for match in URL_RE.findall(text) if not re.search(r"linkedin|github", match, re.IGNORECASE)]
    years, years_confidence = _find_years_of_experience(text)
    title = _find_title(lines)
    company = _find_company(text)
    skills, skills_confidence = _find_skills(text, sections)
    roles, domains = _derive_roles(skills, title)
    summary = _section_text(sections, "summary", "profile", "about", "objective")
    education = _find_education(sections, lines)

    return ParsedResume(
        full_name=name,
        phone=phone_match.group(0).strip() if phone_match else None,
        email=email_match.group(0).strip().lower() if email_match else None,
        location=location,
        linkedin_url=_clean_url(linkedin_match.group(0)) if linkedin_match else None,
        github_url=_clean_url(github_match.group(0)) if github_match else None,
        portfolio_url=_clean_url(other_urls[0]) if other_urls else None,
        summary=summary[:600] if summary else None,
        skills=skills,
        years_of_experience=years,
        current_title=title,
        current_company=company,
        education=education,
        suggested_roles=roles,
        suggested_domains=domains,
        confidence={
            "full_name": name_confidence,
            "email": HIGH if email_match else LOW,
            "phone": MEDIUM if phone_match else LOW,
            "location": MEDIUM if location else LOW,
            "skills": skills_confidence,
            "years_of_experience": years_confidence,
            "current_title": MEDIUM if title else LOW,
            "current_company": MEDIUM if company else LOW,
            "education": MEDIUM if education else LOW,
            "links": HIGH if (linkedin_match or github_match) else LOW,
        },
        source="heuristic",
    )


# ------------------------------------------------------------------------ merge

_SCALARS = (
    "full_name",
    "phone",
    "email",
    "location",
    "linkedin_url",
    "github_url",
    "portfolio_url",
    "summary",
    "years_of_experience",
    "current_title",
    "current_company",
)


def _coerce_llm(data: dict[str, Any] | None) -> ParsedResume | None:
    if not data:
        return None
    allowed = {key: value for key, value in data.items() if key in ParsedResume.model_fields}
    try:
        return ParsedResume.model_validate(allowed)
    except Exception:
        log.warning("llm_resume_output_invalid", keys=sorted(allowed))
        return None


def _merge_strings(llm_value: str | None, base_value: str | None) -> str | None:
    value = (llm_value or "").strip() or None
    return value or base_value


def merge(heuristic: ParsedResume, parsed_llm: ParsedResume | None) -> ParsedResume:
    if parsed_llm is None:
        return heuristic

    merged = heuristic.model_copy(deep=True)
    confidence = dict(heuristic.confidence)
    agreed_or_set = 0

    for field in _SCALARS:
        llm_value = getattr(parsed_llm, field)
        base_value = getattr(heuristic, field)
        if field == "years_of_experience":
            if llm_value is not None:
                merged.years_of_experience = float(llm_value)
                confidence[field] = HIGH if base_value is not None and abs(float(base_value) - float(llm_value)) < 1 else MEDIUM
                agreed_or_set += 1
            continue

        if llm_value not in (None, "", []):
            setattr(merged, field, str(llm_value).strip())
            if base_value and str(base_value).strip().lower() == str(llm_value).strip().lower():
                confidence[field] = HIGH
            else:
                confidence[field] = MEDIUM
            agreed_or_set += 1

    if parsed_llm.skills:
        seen = {skill.lower() for skill in merged.skills}
        merged.skills = list(merged.skills) + [skill for skill in parsed_llm.skills if skill.lower() not in seen]
        merged.skills = merged.skills[:40]
        confidence["skills"] = HIGH

    if parsed_llm.education:
        merged.education = parsed_llm.education
        confidence["education"] = MEDIUM

    roles, domains = parsed_llm.suggested_roles, parsed_llm.suggested_domains
    if roles:
        merged.suggested_roles = roles[:6]
    if domains:
        merged.suggested_domains = domains[:5]

    merged.confidence = confidence
    merged.source = "merged" if agreed_or_set else "heuristic"
    return merged


async def parse_resume(text: str, *, llm_budget_ok: bool = True) -> ParsedResume:
    heuristic = heuristic_parse(text)
    if not llm_budget_ok or not llm.llm_available(llm.TASK_RESUME_PARSE):
        return heuristic

    data = await llm.complete_json(
        llm.TASK_RESUME_PARSE,
        system=RESUME_PARSE_SYSTEM,
        user=build_resume_parse_user(text),
        max_tokens=1500,
    )
    return merge(heuristic, _coerce_llm(data))
