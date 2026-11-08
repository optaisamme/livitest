"""Certification hard filter (applies only when check_certifications = "yes").

  * Certification names are read from the posting itself (no built-in list).
  * Required before hire and listed in certifications_allowed_before_hire: allowed.
  * Any other named certification required at application / by start date: reject.
  * A required certification that the posting does not name: unclear (Needs Verification).
  * Preferred / optional certifications: allowed.
  * Certifications that must be obtained AFTER hire: allowed; reported as a condition
    with name and deadline.
  * Mandatory certification with unclear timing: unclear (Needs Verification).
  * Alternatives: if an allowed cert satisfies an "A or B" requirement, it passes.
  * Allowed certs not documented in the profile are reported as fit gaps.
"""
from __future__ import annotations

import re

from ..models import RuleResult, Evidence, PASS, FAIL, UNCLEAR
from ..text import Segment, excerpt

CERT_WORD = re.compile(r"\b(certif\w*|credential\w*|accredit\w*)\b", re.I)
BENEFIT_CTX = re.compile(r"\b(reimburs\w*|we\s+(pay|cover|support|sponsor)|paid\s+for|stipend|budget|learning\s+(and|&)\s+development|professional\s+development\s+(fund|budget|opportunit)|opportunit(y|ies)\s+to\s+(earn|obtain|pursue))\b", re.I)
# "certificate", "credential" or "accredited" used for a document or an institution, not a certification held by
# the applicant: these words are removed before the sentence is checked.
NOT_A_CERT = re.compile(
    r"\b(degree|diploma|birth|marriage|gift|vaccination|vaccine|immunization|covid[\s-]?19|insurance|tax|training\s+completion)\s+certificat\w*"
    r"|\bcertificat\w*\s+of\s+(insurance|completion|good\s+standing|occupancy|eligibility|vaccination|immunization|birth|"
    r"employment|enrollment|incorporation|deposit|attendance|achievement|appreciation|participation|authority|formation|title|liability)\b"
    r"|\baccredited\s+(college|colleges|university|universities|institution|institutions|school|schools|program|programs|degree|"
    r"academic|educational|four[\s-]year|post[\s-]?secondary|higher\s+education)\b"
    r"|\b(college|university|institution|school|program|hospital|facility|organization|agency|we)\s+(is\s+|are\s+)?accredited\b"
    r"|\baccredited\s+by\b"
    r"|\b(login|log[\s-]in|user|account|system|network|access|security|api|sso)\s+credentials?\b"
    r"|\b(information|documents?|materials?|references|transcripts?)\s+(and|or|&)\s+credentials?\b"
    r"|\bcredentials?\s+(submitted|provided|will\s+be\s+(verified|checked|provided))\b"
    r"|\b(verify|verified|verifying|verification\s+of)\s+(your\s+|all\s+|any\s+)?credentials?\b"
    r"|\bcertif(y|ies|ying)\b"
    # "results rather than credentials", "no certification needed": not a requirement
    r"|\b(rather\s+than|instead\s+of|regardless\s+of|without|no|not)\s+(formal\s+|a\s+|any\s+)?(credentials?|certifications?|certificates?)\b"
    r"|\b(credentials?|certifications?|certificates?)\s+(is\s+|are\s+)?not\s+(required|necessary|needed)\b"
    # handling credentials, a certification company, certification training offered, "any required certifications"
    r"|\bcredentials?\s+(handling|management|storage|sharing)\b"
    r"|\b(inspection|testing)\s+(and\s+)?certification\s+(company|body|bodies|services|firm)\b"
    r"|\bcertification\s+(company|body|bodies|services|firm)\b"
    r"|\bcertifications?\s+(training|programs?|courses?|classes|prep(aration)?|support|reimbursement|opportunities)\b"
    r"|\bany\s+(required\s+)?(licen[sc]es?\s+(or|and|and/or)\s+)?(certifications?|credentials?|certificates?)\b"
    r"|\b(combination|mix)\s+of\s+[^.]{0,80}?(certifications?|credentials?)\b",
    re.I)
ORG_CERT = re.compile(r"\b(certified\s+b\s+corp|great\s+place\s+to\s+work|we\s+are\s+(a\s+)?certified|certified\s+(minority|woman|women)[\s-]owned)\b", re.I)

PREFERRED = re.compile(r"\b(preferred|preferably|a\s+plus|nice[\s-]to[\s-]have|bonus|desired|desirable|ideal(ly)?|optional|helpful|advantage(ous)?|beneficial|welcome|not\s+required|appreciated|big\s+plus"
                       r"|(an?\s+|strong\s+|added\s+)+asset|deemed\s+relevant|(may|will|can)\s+be\s+considered|if\s+you\s+(already\s+)?(hold|have))\b", re.I)
EQUIV = re.compile(r"\bor\s+(equivalent|comparable)\s+(experience|knowledge|work\s+experience)\b|\bin\s+lieu\s+of\b", re.I)
POST_HIRE = re.compile(
    r"(within|in\s+the\s+first|during\s+the\s+first|by\s+the\s+end\s+of\s+(the\s+|your\s+)?first)\s+(\d+|one|two|three|four|five|six|nine|twelve|eighteen|twenty[\s-]?four)?\s*(days?|weeks?|months?|years?|quarters?|year)"
    r"(\s+(of|after|from|following)\s+(the\s+)?(your\s+)?(hire|hiring|start|starting|joining|employment|date\s+of\s+hire|start\s+date|onboarding))?"
    r"|\b(after|upon|following)\s+(hire|hiring|joining|starting|employment)\b"
    r"|\b(once|after)\s+(hired|on\s+board|onboarded)\b"
    r"|\bwilling(ness)?\s+to\s+(obtain|earn|pursue|achieve|get)\b"
    r"|\b(will|would)\s+be\s+(required|expected)\s+to\s+(obtain|earn|achieve|complete|get)\b"
    r"|\bable\s+to\s+(obtain|earn|achieve)\b"
    r"|\bwork\s+towards?\b",
    re.I)
MANDATORY_FUTURE = re.compile(r"\b(must|required\s+to|need\s+to|expected\s+to)\s+(obtain|earn|achieve|acquire|get|complete)\b", re.I)
PREHIRE = re.compile(r"\b(required|requires?|must\s+(have|hold|possess|be)|minimum|current(ly)?|active|valid|hold(s|ing)?\s+(an?\s+)?(active|current)|possess(es|ion)?|at\s+time\s+of\s+(application|hire)|prior\s+to\s+(start|hire)|by\s+(the\s+)?start\s+date|mandatory|essential|you\s+have|you('|’)re\s+certified)\b", re.I)
ALT = re.compile(r"\b(or|and/or|either|one\s+of|any\s+of)\b", re.I)
COUNT_REQ = re.compile(r"\b(\d+|two|three|four|five|multiple|several)\+?\s*(or\s+more\s+)?(certifications|certs|credentials)\b", re.I)
_WORDNUM = {"two": 2, "three": 3, "four": 4, "five": 5, "multiple": 2, "several": 3}


def _allowed_patterns():
    """The user's allowed-before-hire certification names, matched as typed (any capitalization)."""
    from ..criteria import CRITERIA
    # each word may carry ".com" or "'s", and "Certified" or "Platform" may come between words: "Certified
    # Salesforce.com Administrator" and "Salesforce Certified Platform Administrator" are "Salesforce Administrator"
    word = lambda w: re.escape(w) + r"(?:\.com|['’]s)?"
    gap = r"[\s\-]+(?:(?:certified|platform)[\s\-]+){0,2}"
    return [(a.strip(), re.compile(r"(?<![A-Za-z0-9])" + gap.join(map(word, a.split())) + r"(?![A-Za-z0-9])", re.I))
            for a in CRITERIA.get("allowed_prehire_certs", []) if a.strip()]


def _names(s: str) -> tuple[list[str], list[str], bool]:
    """Return (allowed_names, other_names, unused_flag) for one sentence."""
    pats = _allowed_patterns()
    allowed = [n for n, p in pats if p.search(s)]
    masked = s
    for _, p in pats:
        masked = p.sub(" [allowed] ", masked)
    nm = extract_cert_name(masked)
    other = [nm] if nm else []
    return allowed, other, False


_LEAD_WORDS = {"must", "required", "requires", "require", "a", "an", "the", "valid", "active", "current", "requirements",
               "preferred", "minimum", "basic", "qualifications", "and", "or", "with", "have", "hold", "possess", "obtain",
               "earn", "be", "is", "are", "of", "state", "national", "professional", "relevant", "appropriate",
               "applicable", "related", "any", "all", "necessary", "needed", "such", "industry", "recognized",
               "pass", "get", "complete", "maintain", "this", "that", "these", "your", "our", "to", "in", "for", "other",
               "additional", "specific", "certain", "accredited", "approved", "equivalent", "similar", "one", "two"}
_NAME_BEFORE = re.compile(r"((?:[A-Za-z0-9][\w'’/&+.\-]*\s+){0,4}[A-Za-z0-9][\w'’/&+.\-]*)\s+(?i:certification|certificate|credential)s?\b")
_NAME_CERTIFIED = re.compile(r"\bCertified\s+((?:[A-Z0-9][\w'’/&+.\-]*\s*){1,5})")
_NAME_AFTER = re.compile(r"\b(?i:certification|certificate|credential)\s+(?i:in|as\s+an?|as)\s+((?:[A-Z0-9][\w'’/&+.\-]*\s*){1,5})")
# words that never name a certification on their own ("information and credentials", "proof of ... certificate")
_NOT_A_NAME = {"information", "document", "documents", "materials", "application", "applications", "submitted", "proof",
               "copy", "copies", "official", "academic", "educational", "your", "their", "its", "and", "or", "&", "of",
               "progress", "toward", "towards", "pursuing", "working", "on", "results", "demonstrated", "any", "required",
               "license", "licenses", "licensure", "experience", "education", "and/or", "skills", "training", "formerly"}


def extract_cert_name(s: str) -> str | None:
    """Best-effort name of a certification written in the posting; None if not identifiable."""
    for pat in (_NAME_BEFORE, _NAME_CERTIFIED, _NAME_AFTER):
        m = pat.search(s)
        if not m:
            continue
        words = m.group(1).split()
        while words and words[0].lower().strip(".,:;") in _LEAD_WORDS:
            words.pop(0)
        while words and words[-1].lower().strip(".,:;") in ("and", "or", "&", "of", "the", "a", "an"):
            words.pop()
        if words and all(w.lower().strip(".,:;") in _NOT_A_NAME for w in words):
            continue
        if words:
            name = " ".join(words).strip(" .,:;")
            return name + (" certification" if pat is _NAME_BEFORE else "") if pat is not _NAME_CERTIFIED else "Certified " + name
    return None


def _deadline(s: str) -> str | None:
    m = POST_HIRE.search(s)
    return excerpt(m.group(0), 80) if m else None


def evaluate(segments: list[Segment], url: str | None, authoritative: bool,
             profile_certs: list[str] | None = None) -> RuleResult:
    profile_certs = [c.lower() for c in (profile_certs or [])]
    src = "employer_page" if authoritative else "third_party"
    disallowed_prehire, unclear, post_hire, allowed_prehire, preferred, ev = [], [], [], [], [], []

    for seg in segments:
        s = NOT_A_CERT.sub(" ", seg.text)   # documents and institutions, not certifications
        if not CERT_WORD.search(s) or ORG_CERT.search(s):
            continue
        if seg.section == "benefits" or BENEFIT_CTX.search(s):
            continue
        allowed, other, generic = _names(s)
        if not (allowed or other or generic):
            # unnamed certification
            if re.search(r"\bdegree\b", s, re.I) and ALT.search(s):
                continue  # degree-or-certification alternative: not a cert-only requirement
            if PREFERRED.search(s) or seg.section == "preferred" or EQUIV.search(s):
                continue
            if PREHIRE.search(s) or seg.section == "required":
                unclear.append({"name": "Unspecified certification", "why": "unnamed certification requirement", "excerpt": excerpt(s)})
                ev.append(Evidence(excerpt(s), url, src))
            continue

        ev.append(Evidence(excerpt(s), url, src))
        names_all = allowed + other
        item_base = {"names": names_all, "excerpt": excerpt(s), "section": seg.section}

        if PREFERRED.search(s) or seg.section == "preferred":
            preferred.append(item_base)
            continue
        if EQUIV.search(s):
            preferred.append(dict(item_base, why="'or equivalent experience' alternative"))
            continue

        if POST_HIRE.search(s):
            post_hire.append(dict(item_base, deadline=_deadline(s)))
            continue
        if MANDATORY_FUTURE.search(s):
            unclear.append(dict(item_base, why="must obtain certification but timing/deadline not stated"))
            continue

        is_prehire = bool(PREHIRE.search(s)) or seg.section == "required"
        if not is_prehire:
            if other:
                unclear.append(dict(item_base, why="certification mentioned; required vs preferred unclear"))
            continue

        # Pre-hire requirement.
        cnt = COUNT_REQ.search(s)
        n_required = 0
        if cnt:
            tok = cnt.group(1).lower()
            n_required = int(tok) if tok.isdigit() else _WORDNUM.get(tok, 2)
        satisfiable_by_allowed = bool(allowed or generic)
        if other and satisfiable_by_allowed and ALT.search(s) and not re.search(r"\band\b(?!/or)", s, re.I):
            allowed_prehire.append(dict(item_base, why="alternatives include an allowed certification"))
            continue
        if other and satisfiable_by_allowed and ALT.search(s):
            unclear.append(dict(item_base, why="mixed 'and'/'or' wording; unclear whether an allowed certification satisfies it"))
            continue
        if other:
            disallowed_prehire.append(dict(item_base, disallowed=other))
            continue
        if n_required > 2:
            disallowed_prehire.append(dict(item_base, disallowed=[f"{n_required}+ certifications"]))
            continue
        allowed_prehire.append(item_base)

    gaps = []
    for it in allowed_prehire:
        for n in it["names"]:
            if n.lower() not in profile_certs:
                gaps.append(f"{n} certification required before hire; not documented in profile")
    data = {"disallowed_prehire": disallowed_prehire, "unclear": unclear, "post_hire": post_hire,
            "allowed_prehire": allowed_prehire, "preferred": preferred, "fit_gaps": gaps}

    from ..criteria import CRITERIA
    if not CRITERIA.get("cert_filter_on", True):
        parts = ["Certification filter off in settings"]
        if post_hire:
            parts.append("post-hire certification condition(s): " + "; ".join(f"{', '.join(p['names'])} ({p['deadline'] or 'deadline not stated'})" for p in post_hire))
        if disallowed_prehire or allowed_prehire:
            parts.append("required before hire: " + ", ".join(sorted({n for it in disallowed_prehire + allowed_prehire for n in it["names"]})))
        data["fit_gaps"] = []
        return RuleResult("certifications", PASS, "; ".join(parts), ev[:5], data)
    if disallowed_prehire:
        names = sorted({n for it in disallowed_prehire for n in it["disallowed"]})
        return RuleResult("certifications", FAIL, f"Requires before hire: {', '.join(names)}", ev[:5], data)
    if unclear:
        return RuleResult("certifications", UNCLEAR, "; ".join(sorted({u.get('why', '') for u in unclear})), ev[:5], data)
    parts = []
    if allowed_prehire:
        parts.append("required certifications are in your allowed list")
    if post_hire:
        parts.append("post-hire certification condition(s): " + "; ".join(f"{', '.join(p['names'])} ({p['deadline'] or 'deadline not stated'})" for p in post_hire))
    if preferred:
        parts.append("other certifications preferred only")
    return RuleResult("certifications", PASS, "; ".join(parts) or "No certification requirements", ev[:5], data)
