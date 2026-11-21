https://github.com/atlassian-api/atlassian-python-api

✅ pip install atlassian-python-api typer markdownify beautifulsoup4



## Custom markdownify Converter for Bitbucket HTML

Drop this snippet into your Python script whenever you receive HTML from Bitbucket (such as rendered READMEs via ?markup=true or /rest/api/1.0/markup/preview):

```
import re
from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

class BitbucketHTMLConverter(MarkdownConverter):
    def convert_a(self, el, text, parent_tags):
        # Restore Bitbucket @mentions (<a data-username="jcitizen">@Jane Citizen</a>)
        username = el.get("data-username")
        if username:
            return f"@{username}"
        return super().convert_a(el, text, parent_tags)

    def convert_div(self, el, text, parent_tags):
        # Handle Bitbucket syntax-highlighted code blocks (<div class="codehilite language-python">)
        classes = el.get("class") or []
        if "codehilite" in classes or "highlight" in classes:
            lang = ""
            for cls in classes:
                if cls.startswith("language-"):
                    lang = cls.removeprefix("language-")
            pre = el.find("pre")
            code = pre.get_text() if pre else text
            return f"\n```{lang}\n{code.strip(chr(10))}\n```\n"
        return super().convert_div(el, text, parent_tags)

def bitbucket_html_to_md(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    md = BitbucketHTMLConverter(heading_style="ATX", bullets="-").convert_soup(soup)
    return re.sub(r"\n{3,}", "\n\n", md).strip()
```



## Bitbucket Diff JSON → #lean Unified Diff (Zero Extra Libraries)

Bitbucket Server 5.10 returns deeply nested JSON for /pull-requests/{id}/diff. Feeding that raw JSON to an agent wastes ~60% of tokens on keys like "truncated": false and "destination": 12. Convert it to standard unified diff text in pure Python:

```
def render_unified_diff(diff_payload: dict) -> str:
    out = []
    if diff_payload.get("truncated"):
        out.append("# WARNING: Diff truncated by Bitbucket server; query single file paths.\n")
    for diff in diff_payload.get("diffs", []):
        src = (diff.get("source") or {}).get("toString", "/dev/null")
        dst = (diff.get("destination") or {}).get("toString", "/dev/null")
        out.append(f"--- a/{src}\n+++ b/{dst}")
        for hunk in diff.get("hunks", []):
            out.append(f"@@ -{hunk['sourceLine']},{hunk['sourceSpan']} +{hunk['destinationLine']},{hunk['destinationSpan']} @@")
            for seg in hunk.get("segments", []):
                prefix = {"ADDED": "+", "REMOVED": "-", "CONTEXT": " "}.get(seg["type"], " ")
                for line in seg.get("lines", []):
                    out.append(f"{prefix}{line['line']}")
    return "\n".join(out)
```


## docs
bitbucket-5.10-rest.html

```
# Convert HTML API docs to clean GitHub-Flavored Markdown without line wrapping
pandoc -f html -t gfm --wrap=none input.html -o output.md

# Turn a Markdown spec into a styled Word document
pandoc spec.md -o spec.docx

# Build a PDF with an auto-generated Table of Contents
pandoc report.md --toc -o report.pdf

# Turn Markdown notes into a PowerPoint presentation
pandoc slides.md -o deck.pptx
```


see SKILL.md 