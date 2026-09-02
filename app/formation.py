import re

MAX_LINES = 5
MAX_PER_LINE = 6
MAX_TOTAL = 10


class FormationError(ValueError):
    pass


def parse_formation(raw):
    """Parses a formation string like "3-3-2" or "343" into a list of ints
    (goalkeeper not included) and a canonical dash-joined string."""
    if not raw or not raw.strip():
        raise FormationError("Formation erforderlich")

    raw = raw.strip()
    if re.search(r"[-,\s]", raw):
        parts = [p for p in re.split(r"[-,\s]+", raw) if p]
    else:
        parts = list(raw)

    if not parts:
        raise FormationError("Formation erforderlich")

    try:
        lines = [int(p) for p in parts]
    except ValueError:
        raise FormationError("Formation darf nur Zahlen enthalten, z.B. 3-3-2")

    if len(lines) > MAX_LINES:
        raise FormationError(f"Maximal {MAX_LINES} Linien erlaubt")
    if any(n < 1 or n > MAX_PER_LINE for n in lines):
        raise FormationError(f"Jede Linie muss zwischen 1 und {MAX_PER_LINE} Spielern haben")
    total = sum(lines)
    if total > MAX_TOTAL:
        raise FormationError(f"Maximal {MAX_TOTAL} Feldspieler insgesamt erlaubt")

    return lines, "-".join(str(n) for n in lines)
