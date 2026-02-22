---
name: pptx-creator
description: "PowerPoint presentation (.pptx) creation and editing. Use when the user requests slides, presentations, pitch decks, or proposal decks. Supports charts, tables, and image insertion. Works with both template-based and blank creation."
---

# PowerPoint Presentation Creation

## Prerequisites
- python-pptx must be installed
- If not installed: `pip install python-pptx`

## Creation Workflow

### Step 1: Gather Requirements
Identify the following from the user's instructions:
- Purpose and target audience of the presentation
- Approximate number of slides
- Required content (text, charts, tables, images)
- Whether to use a template or start from blank

### Step 2: Create Outline
Present a slide structure proposal to the user:
- Title slide
- Table of contents / agenda
- Body slides (one message per slide principle)
- Summary slide

### Step 3: Generate with Python Script
Create and execute a script following this pattern:

```python
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import CategoryChartData
import os
from datetime import datetime

# Use template if available, otherwise create new
template_path = ".claude/skills/pptx-creator/assets/templates/corporate_template.pptx"
if os.path.exists(template_path):
    prs = Presentation(template_path)
else:
    prs = Presentation()
    prs.slide_width = Inches(13.333)  # 16:9
    prs.slide_height = Inches(7.5)

# --- Title Slide ---
slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = "Presentation Title"
slide.placeholders[1].text = "Subtitle | Date"

# --- Content Slide ---
slide = prs.slides.add_slide(prs.slide_layouts[1])
slide.shapes.title.text = "Section Title"
tf = slide.placeholders[1].text_frame
tf.text = "Key Point"
for point in ["Point 1", "Point 2", "Point 3"]:
    p = tf.add_paragraph()
    p.text = point
    p.level = 1

# --- Chart Slide ---
slide = prs.slides.add_slide(prs.slide_layouts[5])
slide.shapes.title.text = "Sales Trend"
chart_data = CategoryChartData()
chart_data.categories = ['Q1', 'Q2', 'Q3', 'Q4']
chart_data.add_series('2024', (120, 135, 148, 162))
chart_data.add_series('2025', (145, 158, 172, 190))
chart = slide.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED,
    Inches(1.5), Inches(2), Inches(10), Inches(4.5),
    chart_data
).chart
chart.has_legend = True

# --- Table Slide ---
slide = prs.slides.add_slide(prs.slide_layouts[5])
slide.shapes.title.text = "Comparison Table"
table = slide.shapes.add_table(4, 3, Inches(2), Inches(2), Inches(9), Inches(3.5)).table
headers = ["Item", "Plan A", "Plan B"]
for i, h in enumerate(headers):
    table.cell(0, i).text = h

# Save with datetime filename
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = f"output/presentation_{timestamp}.pptx"
os.makedirs("output", exist_ok=True)
prs.save(output_path)
print(f"Saved: {output_path}")
```

### Step 4: Verification
- Confirm the generated file can be parsed without errors
- Verify slide count and structure match the requirements
- Optionally generate thumbnails for visual review

## Design Principles
- @references/design-guidelines.md
- One message per slide
- Maximum 2 font families
- Color palette: 3 colors max (main, accent, text)
- Generous whitespace

## Supported Chart Types
Bar (vertical/horizontal), line, pie, doughnut, scatter, area. 3D charts are NOT supported.

## Important Rules
- NEVER overwrite template files
- Always save output to the output/ directory
- Filenames MUST include a datetime stamp
