# python-docx API Quick Reference

## Installation
```bash
pip install python-docx
pip install docxtpl   # For Jinja2 template support
```

## Core Objects

### Document
```python
from docx import Document

doc = Document()                          # New blank document
doc = Document('template.docx')           # From template
doc.save('output.docx')
```

### Page Setup (A4)
```python
from docx.shared import Cm

section = doc.sections[0]
section.page_width = Cm(21.0)
section.page_height = Cm(29.7)
section.left_margin = Cm(2.5)
section.right_margin = Cm(2.5)
section.top_margin = Cm(3.0)
section.bottom_margin = Cm(2.5)

# Landscape
section.orientation = WD_ORIENT.LANDSCAPE
section.page_width, section.page_height = section.page_height, section.page_width
```

## Units
```python
from docx.shared import Inches, Pt, Cm, Emu, RGBColor

Inches(1.5)
Pt(12)          # Font size
Cm(2.5)
Emu(914400)     # 1 inch
RGBColor(0xFF, 0x00, 0x00)  # Red
```

## Headings & Paragraphs
```python
# Headings (level 0-9, where 0 = Title)
doc.add_heading('Document Title', level=0)
doc.add_heading('Chapter 1', level=1)
doc.add_heading('Section 1.1', level=2)

# Paragraphs
p = doc.add_paragraph('Normal text')
p = doc.add_paragraph('Bold start. ', style='Normal')

# Runs (inline formatting)
run = p.add_run('This is bold')
run.bold = True
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)
run.font.name = 'Yu Gothic'
run.italic = True
run.underline = True
```

## Paragraph Alignment
```python
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

p.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
p.alignment = WD_PARAGRAPH_ALIGNMENT.LEFT
p.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
p.alignment = WD_PARAGRAPH_ALIGNMENT.JUSTIFY
```

## Lists
```python
# Bullet list
doc.add_paragraph('Item 1', style='List Bullet')
doc.add_paragraph('Item 2', style='List Bullet')
doc.add_paragraph('Sub-item', style='List Bullet 2')

# Numbered list
doc.add_paragraph('Step 1', style='List Number')
doc.add_paragraph('Step 2', style='List Number')
doc.add_paragraph('Sub-step', style='List Number 2')
```

## Tables
```python
# Create table
table = doc.add_table(rows=3, cols=4)
table.style = 'Light Shading Accent 1'

# Set cell text
table.cell(0, 0).text = "Header"
table.rows[0].cells[0].text = "Header"  # Same as above

# Add row
row = table.add_row()
row.cells[0].text = "New row data"

# Merge cells
table.cell(0, 0).merge(table.cell(0, 1))

# Set column width
from docx.shared import Cm
table.columns[0].width = Cm(3)

# Available table styles
# 'Table Grid', 'Light Shading', 'Light Shading Accent 1',
# 'Medium Shading 1', 'Medium Shading 1 Accent 1',
# 'Light List', 'Light Grid'
```

## Images
```python
doc.add_picture('image.png', width=Inches(4))
doc.add_picture('image.png', width=Cm(10), height=Cm(7))
# Omit height to maintain aspect ratio
```

## Headers & Footers
```python
section = doc.sections[0]

# Header
header = section.header
header.is_linked_to_previous = False
hp = header.paragraphs[0]
hp.text = "Document Header"
hp.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT

# Footer
footer = section.footer
footer.is_linked_to_previous = False
fp = footer.paragraphs[0]
fp.text = "Page Footer"
fp.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
```

## Page Break
```python
doc.add_page_break()
```

## Document Properties
```python
doc.core_properties.author = "Author Name"
doc.core_properties.title = "Document Title"
doc.core_properties.subject = "Subject"
doc.core_properties.keywords = "keyword1, keyword2"
```

## docxtpl (Jinja2 Templates)
```python
from docxtpl import DocxTemplate, RichText, InlineImage
from docx.shared import Mm

tpl = DocxTemplate("template.docx")

# Context variables
context = {
    'title': 'Report Title',
    'date': '2026-02-22',
    'items': [
        {'name': 'Item 1', 'value': 100},
        {'name': 'Item 2', 'value': 200},
    ],
    'alert': RichText('Warning', color='FF0000', bold=True),
    'logo': InlineImage(tpl, 'logo.png', width=Mm(30)),
}

tpl.render(context)
tpl.save('output.docx')
```

### Template Syntax (inside .docx file)
```
{{ variable }}                          - Simple variable
{{ variable | upper }}                  - Jinja2 filter
{% for item in items %}...{% endfor %}  - Loop
{%tr for item in items %}...{%tr endfor %} - Table row loop
{% if condition %}...{% endif %}        - Conditional
{{ richtext_var }}                      - RichText variable
{{ image_var }}                         - InlineImage variable
```
