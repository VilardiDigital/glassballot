"""Turn the clerk's RTF minutes notes into plain text."""
import re


def rtf_to_text(s: str) -> str:
    if not s or not s.lstrip().startswith("{\\rtf"):
        return (s or "").strip()
    s = re.sub(r"\{\\\*[^{}]*\}", "", s)                 # ignorable destinations
    s = re.sub(r"\{\\(fonttbl|colortbl|stylesheet)(?:[^{}]|\{[^{}]*\})*\}", "", s)
    s = re.sub(r"\\(par|line)(?![a-z])", "\n", s).replace("\\tab", " ")
    s = re.sub(r"\\'([0-9a-f]{2})", lambda m: bytes.fromhex(m.group(1)).decode("cp1252", "replace"), s)
    s = re.sub(r"\\u(-?\d+)\??", lambda m: chr(int(m.group(1)) % 65536), s)
    for k, v in (("rquote", "'"), ("lquote", "'"), ("rdblquote", '"'), ("ldblquote", '"'), ("emdash", ", "), ("endash", "-"), ("bullet", "*")):
        s = re.sub(r"\\" + k + r"(?![a-z]) ?", v, s)
    s = re.sub(r"\\[a-z]+-?\d* ?", "", s)
    s = s.replace("\\{", "{").replace("\\}", "}").replace("\\\\", "\\").replace("{", "").replace("}", "")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n\n", s)
    return s.strip()
