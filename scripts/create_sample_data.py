"""Generate small Acme Retail files used in the interview demo."""

from pathlib import Path

from docx import Document
from openpyxl import Workbook
from pptx import Presentation


SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"


def main() -> None:
    SAMPLE_DIR.mkdir(exist_ok=True)
    workbook = Workbook()
    sales = workbook.active
    sales.title = "Regional Sales"
    sales.append(["Region", "Q1 Revenue", "Q1 Target", "Target Attainment"])
    sales.append(["North", 3800000, 4000000, "95%"])
    sales.append(["South", 4200000, 4000000, "105%"])
    sales.append(["East", 3100000, 3500000, "89%"])
    workbook.save(SAMPLE_DIR / "sales_q1.xlsx")

    (SAMPLE_DIR / "customer_sales.csv").write_text(
        "Segment,Region,Q1 Customers,Retention\nEnterprise,South,125,94%\nSMB,South,410,88%\nEnterprise,North,110,91%\n",
        encoding="utf-8",
    )

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Q1 Business Review"
    slide.placeholders[1].text = "South region exceeded its Q1 revenue target by 5%."
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Regional Performance"
    slide.placeholders[1].text = "South delivered $4.2M against a $4.0M target. Enterprise retention in South was 94%."
    deck.save(SAMPLE_DIR / "q1_business_review.pptx")

    memo = Document()
    memo.add_heading("Q1 Business Review — Executive Summary", level=0)
    memo.add_heading("Executive Summary", level=1)
    memo.add_paragraph(
        "Acme Retail delivered a strong first quarter. The South region led performance, "
        "exceeding its Q1 revenue target by 5%, while Enterprise customer retention across "
        "regions remained above 90%."
    )
    memo.add_heading("Regional Highlights", level=1)
    table = memo.add_table(rows=1, cols=4)
    header_cells = table.rows[0].cells
    for cell, heading in zip(header_cells, ["Region", "Q1 Revenue", "Q1 Target", "Attainment"]):
        cell.text = heading
    for region, revenue, target, attainment in [
        ("North", "3800000", "4000000", "95%"),
        ("South", "4200000", "4000000", "105%"),
        ("East", "3100000", "3500000", "89%"),
    ]:
        row_cells = table.add_row().cells
        for cell, value in zip(row_cells, [region, revenue, target, attainment]):
            cell.text = value
    memo.save(SAMPLE_DIR / "q1_summary_memo.docx")


if __name__ == "__main__":
    main()
