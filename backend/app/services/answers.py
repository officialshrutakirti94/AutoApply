"""Answer resolution: profile rules -> saved answers -> LLM -> a human.

This order is the whole cost model. Most screening questions are facts already on
the profile, so they cost nothing and are answered instantly. Only genuinely new
free-text questions reach a model, and anything sensitive or uncertain stops and
asks the user instead of guessing.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import llm
from app.core.config import settings
from app.core.logging import get_logger
from app.db.enums import ApplicationReason
from app.db.models import Preference, Profile
from app.services import qa_bank

log = get_logger("answers")

PROFILE_CONFIDENCE = 0.95
QA_CONFIDENCE = 0.9
LLM_CONFIDENCE = 0.6

# --- sensitivity -------------------------------------------------------------
# Deterministic first. A question matching any of these never reaches the answer
# model, because a wrong guess here is worse than a stalled application.
SENSITIVE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("demographic", r"\b(gender|sex|female|male|non[\s-]?binary|transgender)\b"),
    ("marital_status", r"\b(marital\s+status|married|unmarried|single|spouse)\b"),
    ("date_of_birth", r"\b(date\s+of\s+birth|d\.?o\.?b\.?|birth\s+date|your\s+age)\b"),
    ("disability", r"\b(disab\w*|handicap\w*|medical\s+condition|chronic\s+illness|health\s+condition)\b"),
    ("caste_religion", r"\b(caste|creed|religion|religious|community\s+certificate)\b"),
    ("pregnancy", r"\b(pregnan\w*|maternity|family\s+planning)\b"),
    ("criminal", r"\b(criminal|convicted|conviction|arrest\w*|police\s+case|fir\b)\b"),
    ("visa_legal", r"\b(visa|work\s+permit|legal\s+declaration|legally\s+(entitled|authori[sz]ed))\b"),
    ("nationality", r"\b(nationality|citizen\w*|country\s+of\s+origin)\b"),
    ("salary_negotiation", r"\b(negotiat\w*|counter\s*offer|flexib\w*\s+(on\s+)?(salary|ctc|compensation))\b"),
    ("background_check", r"\b(background\s+verification|criminal\s+record\s+check)\b"),
)

# --- prompt injection --------------------------------------------------------
INJECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ignore_instructions", r"ignore\s+(all\s+)?(the\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules)"),
    ("disregard_context", r"disregard\s+(the\s+)?(above|previous|system|earlier)"),
    ("reveal_prompt", r"(system\s+prompt|reveal\s+your\s+(instructions?|prompt|rules))"),
    ("ai_address", r"\b(as an ai|you are an ai|dear (ai|assistant)|attention\s+(ai|assistant|automation))\b"),
    ("exfiltrate", r"\b(send|forward|email|share)\b[^.]{0,60}\b(resume|cv|passport|documents?|aadhaar|pan\s+card)\b[^.]{0,40}\bto\b\s+\S"),
    ("new_instructions", r"(new|updated|real)\s+instructions?\s*:"),
    ("script_injection", r"(<script|javascript:|onerror\s*=)"),
    ("apply_elsewhere", r"(click|open)\s+(this|the following)\s+link\s+to\s+(apply|complete)"),
)

_SENSITIVE_RE = tuple((label, re.compile(pattern, re.IGNORECASE)) for label, pattern in SENSITIVE_PATTERNS)
_INJECTION_RE = tuple((label, re.compile(pattern, re.IGNORECASE)) for label, pattern in INJECTION_PATTERNS)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_PHONEISH_RE = re.compile(r"\+?\d[\d\s-]{7,}\d")


@dataclass(frozen=True, slots=True)
class ProfileRule:
    key: str
    pattern: re.Pattern[str]
    resolve: Callable[[Profile, Preference | None], str | None]


@dataclass(slots=True)
class AnswerResult:
    value: str | None
    source: str  # profile | qa_bank | llm | none
    confidence: float
    sensitive: bool = False
    reason: str | None = None
    llm_used: bool = False
    qa_entry_id: uuid.UUID | None = None

    @property
    def resolved(self) -> bool:
        return self.value is not None and not self.sensitive

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "source": self.source,
            "confidence": self.confidence,
            "sensitive": self.sensitive,
            "reason": self.reason,
            "llm_used": self.llm_used,
        }


# ------------------------------------------------------------------- detection


def detect_sensitive(question: str) -> str | None:
    for label, pattern in _SENSITIVE_RE:
        if pattern.search(question):
            return label
    return None


def detect_injection(text: str | None) -> str | None:
    if not text:
        return None
    for label, pattern in _INJECTION_RE:
        if pattern.search(text):
            return label
    return None


# --------------------------------------------------------------- profile rules


def _number(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _lpa(value) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return f"{number:g} LPA"


def _notice_period(profile: Profile, _: Preference | None) -> str | None:
    days = profile.notice_period_days
    if days is None:
        return None
    if days <= 0:
        return "Immediate"
    if days % 30 == 0:
        months = days // 30
        return f"{months} month" + ("s" if months > 1 else "")
    return f"{days} days"


def _notice_days(profile: Profile, _: Preference | None) -> str | None:
    return None if profile.notice_period_days is None else str(profile.notice_period_days)


def _years(profile: Profile, _: Preference | None) -> str | None:
    number = _number(profile.years_of_experience)
    return None if number is None else f"{number:g}"


def _first_name(profile: Profile, _: Preference | None) -> str | None:
    parts = (profile.full_name or "").split()
    return parts[0] if parts else None


def _last_name(profile: Profile, _: Preference | None) -> str | None:
    parts = (profile.full_name or "").split()
    return parts[-1] if len(parts) > 1 else None


def _relocation(profile: Profile, preferences: Preference | None) -> str | None:
    if preferences is None:
        return None
    modes = {mode.lower() for mode in (preferences.work_mode or [])}
    if not modes:
        return None
    if modes == {"remote"}:
        return "No"
    if modes & {"onsite", "hybrid"}:
        return "Yes"
    return None


def _education_degree(profile: Profile, _: Preference | None) -> str | None:
    for item in profile.education or []:
        if isinstance(item, dict) and item.get("degree"):
            return str(item["degree"])
    return None


def _phone_country_code(phone: str | None, options: list[str]) -> str | None:
    if not phone or not phone.strip().startswith("+"):
        return None

    number = re.sub(r"\D", "", phone)
    if not number:
        return None

    matches: list[tuple[int, str]] = []
    for option in options:
        match = re.search(r"\(\s*\+(\d{1,4})\s*\)", option)
        if match and number.startswith(match.group(1)):
            matches.append((len(match.group(1)), option))
    if not matches:
        return None

    longest = max(length for length, _ in matches)
    best = [option for length, option in matches if length == longest]
    return best[0] if len(best) == 1 else None


# Order matters: specific patterns before general ones.
PROFILE_RULES: tuple[ProfileRule, ...] = (
    ProfileRule("expected_ctc", re.compile(r"\b(expected|desired|looking for)\b.{0,20}\b(ctc|salary|compensation|pay)", re.I), lambda p, _: _lpa(p.expected_ctc_lpa)),
    ProfileRule("current_ctc", re.compile(r"\b(current|present|existing)\b.{0,20}\b(ctc|salary|compensation|pay)", re.I), lambda p, _: _lpa(p.current_ctc_lpa)),
    ProfileRule("expected_ctc_short", re.compile(r"\b(expected|desired)\s*(ctc|salary)\b", re.I), lambda p, _: _lpa(p.expected_ctc_lpa)),
    ProfileRule("current_ctc_short", re.compile(r"\b(current|present)\s*(ctc|salary)\b", re.I), lambda p, _: _lpa(p.current_ctc_lpa)),
    ProfileRule("notice_days", re.compile(r"\bnotice\b.{0,20}\b(days?|in\s+days)\b", re.I), _notice_days),
    ProfileRule("notice_period", re.compile(r"\bnotice\s+period\b|\bhow\s+(soon|early)\s+can\s+you\s+join\b|\bjoining\s+(date|time)\b|\bavailable\s+to\s+join\b", re.I), _notice_period),
    ProfileRule("work_authorization", re.compile(r"\b(work\s+authori[sz]ation|authori[sz]ed\s+to\s+work|right\s+to\s+work|legally\s+allowed\s+to\s+work)\b", re.I), lambda p, _: p.work_authorization),
    ProfileRule("relocation", re.compile(r"\b(willing|ready|open)\s+to\s+(relocate|relocation|move)\b|\brelocat(e|ion)\b", re.I), _relocation),
    ProfileRule("current_company", re.compile(r"\b(current|present|latest)\s+(company|employer|organi[sz]ation)\b|\bwhere\s+(do\s+you|you)\s+work\b|\bwhich\s+company\b|\b(company|employer)\s+are\s+you\s+(currently\s+)?(working|employed)\b|\bcurrently\s+(work|working|employed)\b", re.I), lambda p, _: p.current_company),
    ProfileRule("current_title", re.compile(r"\b(current|present|latest)\s+(job\s+)?(title|designation|role|position)\b", re.I), lambda p, _: p.current_title),
    ProfileRule("total_experience", re.compile(r"\b(total|overall)\b.{0,20}\b(experience|exp)\b|\byears?\s+of\s+experience\b|\bexperience\s+in\s+years?\b", re.I), _years),
    ProfileRule("first_name", re.compile(r"\bfirst\s+name\b|\bgiven\s+name\b", re.I), _first_name),
    ProfileRule("last_name", re.compile(r"\b(last|sur|family)\s+name\b", re.I), _last_name),
    ProfileRule("full_name", re.compile(r"\b(full\s+name|your\s+name|candidate\s+name|name\s+of\s+the\s+candidate)\b", re.I), lambda p, _: p.full_name),
    ProfileRule("email", re.compile(r"\be[-\s]?mail\b", re.I), lambda p, _: p.email),
    ProfileRule("phone", re.compile(r"\b(phone|mobile|contact\s+(number|no)|cell)\b", re.I), lambda p, _: p.phone),
    ProfileRule("location", re.compile(r"\b(current\s+)?(location|city|place\s+of\s+residence|residing|based\s+in)\b", re.I), lambda p, _: p.location),
    ProfileRule("linkedin", re.compile(r"\blinked\s?in\b", re.I), lambda p, _: p.linkedin_url),
    ProfileRule("github", re.compile(r"\bgit\s?hub\b", re.I), lambda p, _: p.github_url),
    ProfileRule("portfolio", re.compile(r"\b(portfolio|personal\s+(website|site)|website)\b", re.I), lambda p, _: p.portfolio_url),
    ProfileRule("education", re.compile(r"\b(highest\s+)?(qualification|degree|education)\b", re.I), _education_degree),
)

_SKILL_YEARS_RE = re.compile(
    r"(?:years?|yrs?)\s+(?:of\s+)?(?:experience\s+)?(?:in|with|using|on)\s+([a-zA-Z0-9+#.\s]{2,30})",
    re.IGNORECASE,
)


def _skill_specific_years(question: str, profile: Profile) -> str | None:
    match = _SKILL_YEARS_RE.search(question)
    if not match:
        return None
    asked = match.group(1).strip().lower()
    known = {str(skill).strip().lower() for skill in (profile.skills or [])}
    if not any(skill and skill in asked for skill in known):
        return None
    return _years(profile, None)


def match_rule(question: str, profile: Profile, preferences: Preference | None) -> ProfileRule | None:
    for rule in PROFILE_RULES:
        if rule.pattern.search(question):
            return rule
    return None


# ------------------------------------------------------------------ formatting


def fit_to_options(value: str, options: list[str]) -> str:
    """Pick the form's own option when one clearly matches.

    Selects and radio groups reject free text, so a profile value like "12 LPA"
    has to become "12" or "10-15 LPA" if that is what the form offers.
    """
    if not options:
        return value

    lowered = value.strip().lower()
    for option in options:
        if option.strip().lower() == lowered:
            return option

    numbers = _NUMBER_RE.findall(value)
    if numbers:
        for option in options:
            if any(number in option for number in numbers):
                return option

    # Forms often ask for days where the profile says months.
    months = re.fullmatch(r"(\d+(?:\.\d+)?)\s*months?", lowered)
    if months:
        days = int(float(months.group(1)) * 30)
        for option in options:
            if str(days) in option:
                return option

    for option in options:
        option_lower = option.lower()
        if lowered in option_lower or option_lower in lowered:
            return option

    for keyword in ("yes", "no", "immediate"):
        if keyword in lowered:
            for option in options:
                if option.strip().lower() == keyword:
                    return option
    return value


def screening_facts(profile: Profile, preferences: Preference | None) -> dict:
    """The only profile data that may reach a model. No name, email or phone."""
    degrees = [
        str(item.get("degree"))
        for item in (profile.education or [])
        if isinstance(item, dict) and item.get("degree")
    ]
    return {
        "years_of_experience": _number(profile.years_of_experience),
        "current_title": profile.current_title,
        "current_company": profile.current_company,
        "location": profile.location,
        "notice_period_days": profile.notice_period_days,
        "current_ctc_lpa": _number(profile.current_ctc_lpa),
        "expected_ctc_lpa": _number(profile.expected_ctc_lpa),
        "work_authorization": profile.work_authorization,
        "skills": list(profile.skills or [])[:20],
        "education": degrees,
        "work_modes": list(preferences.work_mode) if preferences else [],
        "preferred_locations": list(preferences.locations) if preferences else [],
    }


def _numbers(text: str) -> set[str]:
    """Numeric tokens, normalised so 24 and 24.0 compare equal."""
    values: set[str] = set()
    for raw in _NUMBER_RE.findall(str(text)):
        values.add(raw.rstrip("0").rstrip(".") if "." in raw else raw)
    return values


def _is_grounded(answer: str, facts: dict, options: list[str]) -> bool:
    """Reject an answer that introduces a number or contact detail we never supplied."""
    allowed_numbers = _numbers(facts)
    for option in options:
        allowed_numbers |= _numbers(option)

    for number in _numbers(answer):
        if number not in allowed_numbers:
            return False

    if "@" in answer and "@" not in str(facts):
        return False
    if _PHONEISH_RE.search(answer) and not _PHONEISH_RE.search(str(facts)):
        return False
    return True


# ------------------------------------------------------------------ resolution


async def answer_question(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    question: str,
    options: list[str] | None,
    profile: Profile | None,
    preferences: Preference | None,
    llm_calls_left: int = 0,
    allow_llm: bool = True,
) -> AnswerResult:
    options = options or []
    cleaned = (question or "").strip()
    if not cleaned:
        return AnswerResult(None, "none", 0.0, reason=ApplicationReason.UNKNOWN_QUESTION.value)

    sensitive_label = detect_sensitive(cleaned)
    if sensitive_label is not None:
        saved = await qa_bank.find_entry(db, user_id=user_id, question=cleaned)
        if saved is not None and saved.approved and saved.sensitive and saved.answer:
            await qa_bank.mark_used(db, saved)
            return AnswerResult(
                fit_to_options(saved.answer, options),
                "qa_bank",
                QA_CONFIDENCE,
                qa_entry_id=saved.id,
            )
        return AnswerResult(
            None,
            "none",
            0.0,
            sensitive=True,
            reason=ApplicationReason.SENSITIVE_QUESTION.value,
        )

    if profile is None:
        return AnswerResult(None, "none", 0.0, reason=ApplicationReason.UNKNOWN_QUESTION.value)

    if re.search(
        r"\b(phone|mobile|dial(?:ing|ling))\s+country\s+code\b",
        cleaned,
        re.IGNORECASE,
    ):
        country_code = _phone_country_code(profile.phone, options)
        if country_code:
            return AnswerResult(country_code, "profile", PROFILE_CONFIDENCE)
        return AnswerResult(None, "none", 0.0, reason=ApplicationReason.UNKNOWN_QUESTION.value)

    skill_years = _skill_specific_years(cleaned, profile)
    if skill_years:
        return AnswerResult(fit_to_options(skill_years, options), "profile", PROFILE_CONFIDENCE)

    rule = match_rule(cleaned, profile, preferences)
    if rule is not None:
        value = rule.resolve(profile, preferences)
        if value:
            return AnswerResult(
                fit_to_options(value, options),
                "profile",
                PROFILE_CONFIDENCE,
            )
        # We understood the question but the profile has no answer for it.
        return AnswerResult(None, "none", 0.0, reason=ApplicationReason.UNKNOWN_QUESTION.value)

    saved = await qa_bank.find_entry(db, user_id=user_id, question=cleaned)
    if saved is not None and saved.approved and saved.answer:
        await qa_bank.mark_used(db, saved)
        return AnswerResult(
            fit_to_options(saved.answer, options),
            "qa_bank",
            QA_CONFIDENCE,
            qa_entry_id=saved.id,
        )
    if saved is not None and not saved.approved:
        # The agent proposed this answer before; until a human approves it, ask.
        return AnswerResult(
            None,
            "none",
            0.0,
            sensitive=bool(saved.sensitive),
            reason=ApplicationReason.LOW_CONFIDENCE.value,
            qa_entry_id=saved.id,
        )

    if not allow_llm or llm_calls_left <= 0 or not settings.llm_enabled:
        return AnswerResult(None, "none", 0.0, reason=ApplicationReason.UNKNOWN_QUESTION.value)

    verdict = await llm.classify_question(cleaned, options)
    if verdict == "sensitive":
        return AnswerResult(
            None, "none", 0.0, sensitive=True, reason=ApplicationReason.SENSITIVE_QUESTION.value
        )

    facts = screening_facts(profile, preferences)
    proposed = await llm.answer_screening_question(cleaned, options, facts)
    if not proposed or not _is_grounded(proposed, facts, options):
        log.info("answer_rejected", question=cleaned[:80], grounded=False)
        return AnswerResult(None, "none", 0.0, reason=ApplicationReason.LOW_CONFIDENCE.value)

    await qa_bank.upsert_ai_answer(db, user_id=user_id, question=cleaned, answer=proposed)
    return AnswerResult(
        fit_to_options(proposed, options),
        "llm",
        LLM_CONFIDENCE,
        llm_used=True,
    )


def needs_human(result: AnswerResult) -> bool:
    return not result.resolved
