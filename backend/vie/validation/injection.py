"""Detection of instruction-like text inside documents (prompt-injection attempts).

Document text is ALWAYS treated as data; this detector only raises a warning so
a human can review the document. It never changes extracted values.
"""

from __future__ import annotations

import re

from ..extraction.normalize import strip_accents

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("ignore_instructions", re.compile(
        r"\bIGNOR(A|E|EN|AR|ES)\b.{0,40}\b(INSTRUCCION|INDICACION|REGLA|ORDEN|INSTRUCTION|PROMPT)", re.I)),
    ("ignore_previous", re.compile(r"\b(IGNORE|DISREGARD|FORGET)\b.{0,30}\b(PREVIOUS|PRIOR|ABOVE|ALL)\b", re.I)),
    ("role_marker", re.compile(r"(^|\s)(SYSTEM|SISTEMA|ASSISTANT|ASISTENTE|DEVELOPER)\s*:", re.I)),
    ("role_tag", re.compile(r"<\s*/?\s*(SYSTEM|ASSISTANT|USER|INSTRUCTIONS?)\s*>", re.I)),
    ("persona_override", re.compile(r"\b(AHORA ERES|ACTUA COMO|YOU ARE NOW|ACT AS|PRETEND TO BE)\b", re.I)),
    ("shell_command", re.compile(r"\b(RM\s+-RF|SUDO\s|CURL\s+HTTP|WGET\s+HTTP|POWERSHELL|BASH\s+-C|CHMOD\s+\d|"
                                 r"EXEC\(|EVAL\(|DOCKER\s+RUN)", re.I)),
    ("forced_verdict", re.compile(
        r"\b(DECLARA|MARCA|APRUEBA|CONSIDERA|RESPONDE|INDICA)\b.{0,40}\b(VALID[OA]|CORRECT[OA]|APROBAD[OA]|"
        r"TOTAL\s+(ES|=)|APPROVED)", re.I)),
    ("jailbreak", re.compile(r"\b(JAILBREAK|DEVELOPER MODE|MODO DESARROLLADOR|DAN MODE)\b", re.I)),
]


def scan(lines: list[tuple[str, str]]) -> list[dict]:
    """lines: [(evidence_id, text)]. Returns findings with the evidence id and pattern name."""
    findings = []
    for line_id, text in lines:
        t = strip_accents(text or "").upper()
        for name, pattern in PATTERNS:
            if pattern.search(t):
                findings.append({"evidence_id": line_id, "pattern": name, "text": (text or "")[:160]})
                break
    return findings
