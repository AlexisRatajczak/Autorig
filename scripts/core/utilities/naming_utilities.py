# ====================================================================================================================
# NAMING UTILITIES
# ====================================================================================================================
#
#   is_valid(name, rule)                              - True if 'name' follows 'rule'
#   suggest(name, rule, strip_suffixes)               - name that follows 'rule', or None
#   expected_shape_name(transform_name, index, rule)  - expected name of a transform's index-th shape
#
# ====================================================================================================================

import re

# --------------------------------------------------
# IS VALID
# --------------------------------------------------

def is_valid(name, rule):
    """
    True if 'name' follows 'rule' (prefix / suffix / pattern).

    rule : {"prefix": "", "suffix": "_geo", "pattern": "^[a-zA-Z][a-zA-Z0-9_]*$"}.
    """

    prefix = rule.get("prefix", "")
    suffix = rule.get("suffix", "")
    pattern = rule.get("pattern", "")

    if prefix and not name.startswith(prefix):
        return False

    if suffix and not name.endswith(suffix):
        return False

    if len(name) <= len(prefix) + len(suffix):
        return False

    if pattern and not re.fullmatch(pattern, name):
        return False

    return True

# --------------------------------------------------
# SUGGEST
# --------------------------------------------------

def suggest(name, rule, strip_suffixes=()):
    """
    Name built from 'name' that follows 'rule', or None if none can be built.

    rule           : see is_valid.
    strip_suffixes : known suffixes removed from 'name' first (plus the rule suffix).
    """

    prefix = rule.get("prefix", "")
    suffix = rule.get("suffix", "")

    base = re.sub(r"[^A-Za-z0-9_]", "_", name)

    if prefix and base.startswith(prefix):
        base = base[len(prefix):]

    candidates = sorted(set(strip_suffixes) | ({suffix} if suffix else set()), key=len, reverse=True)

    for known in candidates:
        if known and base.lower().endswith(known.lower()):
            base = base[: -len(known)]
            break

    base = re.sub(r"_+", "_", base).strip("_") or "node"

    new_name = "{}{}{}".format(prefix, base, suffix)

    return new_name if is_valid(new_name, rule) else None

# --------------------------------------------------
# EXPECTED SHAPE NAME
# --------------------------------------------------

def expected_shape_name(transform_name, index, rule):
    """
    Expected name of the index-th shape of 'transform_name' ('nameShape', 'nameShape1', ...).

    rule : may hold a "template" (default "{transform}Shape").
    """

    template = rule.get("template", "{transform}Shape")
    name = template.format(transform=transform_name)

    return name if index == 0 else "{}{}".format(name, index)
