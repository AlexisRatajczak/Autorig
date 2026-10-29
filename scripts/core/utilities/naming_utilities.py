# ====================================================================================================================
# ====================================================================================================================

# ==========================================================
# TABLE OF CONTENTS
# ==========================================================
#
#   is_valid(name, rule)                          - True si 'name' respecte 'rule'
#   suggest(name, rule, strip_suffixes)           - propose un nom respectant 'rule', ou None
#   expected_shape_name(transform_name, index, rule) - nom attendu de la index-ieme shape d'un transform

# ====================================================================================================================
# ====================================================================================================================

import re

# --------------------------------------------------
# IS VALID
# --------------------------------------------------

def is_valid(name, rule):
    """
    True si 'name' respecte 'rule' (prefix/suffix/pattern).

    name : nom a valider.
    rule : dict {"prefix": "", "suffix": "_geo", "pattern": "^[a-zA-Z][a-zA-Z0-9_]*$"}.
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
    Propose un nom respectant 'rule' a partir de 'name', ou None si aucun nom
    valide ne peut etre construit.

    name           : nom de depart.
    rule           : voir is_valid.
    strip_suffixes : suffixes connus a retirer de 'name' avant de reconstruire
                      (en plus du suffixe de 'rule').
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
    Nom attendu de la index-ieme shape de 'transform_name' ('nameShape',
    'nameShape1', ...).

    rule : dict avec eventuellement "template" (defaut "{transform}Shape").
    """

    template = rule.get("template", "{transform}Shape")
    name = template.format(transform=transform_name)

    return name if index == 0 else "{}{}".format(name, index)
