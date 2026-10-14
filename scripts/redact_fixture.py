"""Strip personal data from a saved eaukcionai.lt page before it becomes a test fixture.

Usage: uv run python scripts/redact_fixture.py RAW.html OUT.html
"""

import re
import sys

REDACTED = "REDACTED"

FREE_TEXT_LABELS = (
    "Savininkai:",
    "Aprašymas:",
    "Turto apžiūra:",
    "Apie objektą:",
    "Atsiskaitymo sąlygos:",
    "Mokėjimų periodiškumas, įsipareigojimų įvykdymo užtikrinimo priemonės:",
)


def redact(html: str) -> str:
    html = re.sub(
        r'(<div class="additional_block">).*?(</div>)',
        rf"\1{REDACTED}\2",
        html,
        flags=re.DOTALL,
    )
    for label in FREE_TEXT_LABELS:
        html = re.sub(
            rf'(<span class="left">\s*{re.escape(label)}\s*</span>\s*<span class="right[^"]*"[^>]*>).*?(</span>)',
            rf"\1{REDACTED}\2",
            html,
            flags=re.DOTALL,
        )
    html = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "00000000-0000-0000-0000-000000000000", html
    )
    html = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", REDACTED, html)
    return html


if __name__ == "__main__":
    raw, out = sys.argv[1:3]
    with open(raw, encoding="utf-8") as f:
        text = f.read()
    with open(out, "w", encoding="utf-8") as f:
        f.write(redact(text))
