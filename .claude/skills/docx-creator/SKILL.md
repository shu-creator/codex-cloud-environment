---
name: docx-creator
description: "Word document (.docx) creation and editing. Use when the user requests reports, meeting minutes, proposals, contracts, manuals, letters, or memos. Supports tables, images, headers/footers, and TOC structure. Works with both template-based and blank creation."
---

# Word Document Creation

## Prerequisites
- python-docx must be installed
- If not installed: `pip install python-docx`
- For template-based creation: `pip install docxtpl` (Jinja2 template engine)

## Creation Workflow

### Step 1: Gather Requirements
Identify the following from the user's instructions:
- Document type (report / minutes / proposal / manual / etc.)
- Reader and purpose
- Required section structure
- Format requirements (page setup, headers/footers)
- Whether to use a template

### Step 2: Present Structure
Show the user a document outline for approval.

### Step 3: Generate with Python Script

```python
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import os
from datetime import datetime

doc = Document()

# --- Page setup (A4) ---
section = doc.sections[0]
section.page_width = Cm(21.0)
section.page_height = Cm(29.7)
section.left_margin = Cm(2.5)
section.right_margin = Cm(2.5)
section.top_margin = Cm(3.0)
section.bottom_margin = Cm(2.5)

# --- Header ---
header = section.header
header.is_linked_to_previous = False
hp = header.paragraphs[0]
hp.text = "Confidential | Project Name"
hp.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

# --- Document properties ---
doc.core_properties.author = "Author"
doc.core_properties.title = "Document Title"

# --- Title ---
title = doc.add_heading('Document Title', level=0)
title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER

# --- Body ---
doc.add_heading('1. Introduction', level=1)
doc.add_paragraph('This document describes...')

doc.add_heading('2. Background', level=1)
doc.add_heading('2.1 Current Analysis', level=2)
p = doc.add_paragraph()
run = p.add_run('Important: ')
run.bold = True
run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
p.add_run('Content to emphasize here.')

# --- Bullet points ---
doc.add_heading('3. Key Findings', level=1)
for item in ['Finding 1', 'Finding 2', 'Finding 3']:
    doc.add_paragraph(item, style='List Bullet')

# --- Table ---
doc.add_heading('4. Data Summary', level=1)
table = doc.add_table(rows=1, cols=4)
table.style = 'Light Shading Accent 1'
for i, h in enumerate(['Item', 'Current', 'Target', 'Progress']):
    table.rows[0].cells[i].text = h

# Save with datetime filename
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = f"output/document_{timestamp}.docx"
os.makedirs("output", exist_ok=True)
doc.save(output_path)
print(f"Saved: {output_path}")
```

### Step 4: Template-Based Creation (Jinja2)

Using `docxtpl`, you can inject variables into a Word template:

```python
from docxtpl import DocxTemplate, RichText

tpl = DocxTemplate("assets/templates/corporate_template.docx")
context = {
    'title': 'Monthly Report',
    'date': '2026-02',
    'author': 'Author Name',
    'sections': [
        {'heading': 'Performance', 'body': 'Sales up 15% MoM...'},
        {'heading': 'Challenges', 'body': 'Staffing shortage continues...'},
    ],
    'alert': RichText('Action required', color='FF0000', bold=True),
}
tpl.render(context)
tpl.save("output/monthly_report.docx")
```

### Step 5: Verification
- Confirm the generated file can be parsed without errors
- Verify section structure matches requirements
- Check headers/footers and page setup

## Document Type Templates
- **Report**: Title > Summary > Background > Analysis > Conclusion > Appendix
- **Minutes**: Meeting Info > Attendees > Agenda > Decisions > Action Items
- **Proposal**: Cover > Overview > Problem > Solution > Schedule > Budget > Summary

## Important Rules
- NEVER overwrite template files
- Always save output to the output/ directory
- Default page size: A4 (21cm x 29.7cm)
- Japanese fonts: MS Mincho, MS Gothic, Yu Mincho, Yu Gothic
