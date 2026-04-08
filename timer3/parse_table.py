"""
Parse the <table> HTML returned from TIMER3's geneOutput_fixedHeatTable.
Returns a list of row dicts with column headers as keys.
"""
import re
from typing import Any


def parse_fixed_heat_table(html: str) -> list[dict[str, Any]]:
    """Parse a <table>...</table> HTML string into a list of row dicts."""
    if not html:
        return []

    # Extract header cells (th)
    header_match = re.search(r"<thead[^>]*>(.*?)</thead>", html, re.DOTALL | re.IGNORECASE)
    if header_match:
        headers = re.findall(r"<th[^>]*>(.*?)</th>", header_match.group(1), re.DOTALL)
        headers = [_clean(h) for h in headers]
    else:
        headers = []

    # Extract body rows
    body_match = re.search(r"<tbody[^>]*>(.*?)</tbody>", html, re.DOTALL | re.IGNORECASE)
    if not body_match:
        return []

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", body_match.group(1), re.DOTALL | re.IGNORECASE)
    result = []
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL | re.IGNORECASE)
        if not cells:
            continue
        cells = [_clean(c) for c in cells]
        if headers and len(cells) == len(headers):
            result.append(dict(zip(headers, cells)))
        else:
            result.append({"cols": cells})

    return result


def _clean(text: str) -> str:
    """Strip HTML tags and whitespace."""
    return re.sub(r"<[^>]+>", "", text).strip()
