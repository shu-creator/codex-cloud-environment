# python-pptx API Quick Reference

## Installation
```bash
pip install python-pptx
```

## Core Objects

### Presentation
```python
from pptx import Presentation

prs = Presentation()                        # New blank presentation
prs = Presentation('template.pptx')         # From template
prs.slide_width = Inches(13.333)            # 16:9
prs.slide_height = Inches(7.5)
prs.save('output.pptx')
```

### Slides
```python
slide_layout = prs.slide_layouts[0]          # Title Slide
slide_layout = prs.slide_layouts[1]          # Title and Content
slide_layout = prs.slide_layouts[5]          # Blank
slide_layout = prs.slide_layouts[6]          # Title Only

slide = prs.slides.add_slide(slide_layout)
```

### Standard Slide Layouts (index)
| Index | Name | Description |
|-------|------|-------------|
| 0 | Title Slide | Title + subtitle |
| 1 | Title and Content | Title + body placeholder |
| 2 | Section Header | Section divider |
| 3 | Two Content | Title + two body columns |
| 4 | Comparison | Title + two labeled columns |
| 5 | Title Only | Title only, rest is blank |
| 6 | Blank | Completely blank |

## Units
```python
from pptx.util import Inches, Pt, Cm, Emu

Inches(1.5)    # 1.5 inches
Pt(12)         # 12 points (font size)
Cm(2.5)        # 2.5 centimeters
Emu(914400)    # English Metric Units (914400 = 1 inch)
```

## Text
```python
from pptx.util import Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

# Using placeholders
slide.shapes.title.text = "Title Text"
slide.placeholders[1].text = "Body Text"

# TextFrame manipulation
tf = slide.placeholders[1].text_frame
tf.word_wrap = True
p = tf.paragraphs[0]
p.text = "First paragraph"
p.font.size = Pt(18)
p.font.bold = True
p.font.color.rgb = RGBColor(0x00, 0x66, 0xCC)
p.alignment = PP_ALIGN.LEFT

# Add paragraphs
p2 = tf.add_paragraph()
p2.text = "Second paragraph"
p2.level = 1  # Indent level (0-8)
```

## Shapes
```python
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE

# Add textbox
txBox = slide.shapes.add_textbox(
    Inches(1), Inches(2), Inches(5), Inches(1.5)
)
tf = txBox.text_frame
tf.text = "Textbox content"

# Add auto shape
shape = slide.shapes.add_shape(
    MSO_SHAPE.ROUNDED_RECTANGLE,
    Inches(1), Inches(2), Inches(3), Inches(1)
)
shape.text = "Shape text"
shape.fill.solid()
shape.fill.fore_color.rgb = RGBColor(0x00, 0x99, 0xFF)
```

## Tables
```python
rows, cols = 4, 3
table_shape = slide.shapes.add_table(
    rows, cols,
    Inches(2), Inches(2),     # left, top
    Inches(9), Inches(3.5)    # width, height
)
table = table_shape.table

# Set cell text
table.cell(0, 0).text = "Header 1"
table.cell(1, 0).text = "Row 1, Col 1"

# Merge cells
table.cell(0, 0).merge(table.cell(0, 2))  # Merge across columns
```

## Charts
```python
from pptx.enum.chart import XL_CHART_TYPE
from pptx.chart.data import CategoryChartData, ChartData

# Bar/Column chart
chart_data = CategoryChartData()
chart_data.categories = ['Q1', 'Q2', 'Q3', 'Q4']
chart_data.add_series('2024', (120, 135, 148, 162))
chart_data.add_series('2025', (145, 158, 172, 190))

chart_shape = slide.shapes.add_chart(
    XL_CHART_TYPE.COLUMN_CLUSTERED,
    Inches(1.5), Inches(2),
    Inches(10), Inches(4.5),
    chart_data
)
chart = chart_shape.chart
chart.has_legend = True
chart.legend.include_in_layout = False

# Chart types
# XL_CHART_TYPE.COLUMN_CLUSTERED
# XL_CHART_TYPE.BAR_CLUSTERED
# XL_CHART_TYPE.LINE
# XL_CHART_TYPE.LINE_MARKERS
# XL_CHART_TYPE.PIE
# XL_CHART_TYPE.DOUGHNUT
# XL_CHART_TYPE.XY_SCATTER
# XL_CHART_TYPE.AREA
```

## Images
```python
slide.shapes.add_picture(
    'image.png',
    Inches(1), Inches(2),     # left, top
    Inches(5), Inches(3)      # width, height (optional, maintains ratio if one omitted)
)
```

## Colors
```python
from pptx.dml.color import RGBColor

red = RGBColor(0xFF, 0x00, 0x00)
blue = RGBColor(0x00, 0x66, 0xCC)
dark_gray = RGBColor(0x33, 0x33, 0x33)
```
