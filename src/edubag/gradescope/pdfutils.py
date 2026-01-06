"""
This module is for finding and extracting the pages of a PDF file that
are Gradescope bubble sheets.

It doesn't work, and it might not be necessary. Gradescope splits the PDF
at each bubblesheet (which I knew how it recognized them), and allows you
to create the submissions in a batch.
"""

import io
from pathlib import Path
from pypdfium2 import PdfDocument
from pylibdmtx.pylibdmtx import decode as dmtx_decode
from PIL import Image, ImageEnhance, ImageOps
from pypdf import PdfReader, PdfWriter
import typer
from typing import Annotated

try:
    from pyzbar.pyzbar import decode as zbar_decode
    HAS_ZBAR = True
except ImportError:
    HAS_ZBAR = False

# Allowed DataMatrix values
VALID_CODES = {
    "MC-2020-VERSION-A",
    "MC-2020-VERSION-B",
    "MC-2020-VERSION-C",
    "MC-2020-VERSION-D",
    "MC-2020-VERSION-E",
}

def preprocess_image(img):
    """Convert to grayscale and enhance contrast."""
    gray = ImageOps.grayscale(img)
    enhancer = ImageEnhance.Contrast(gray)
    return enhancer.enhance(2.5)

def find_datamatrix_values(img):
    """Try multiple decoders and return decoded values."""
    results = []
    processed = preprocess_image(img)

    # Try pylibdmtx first
    dmtx_results = dmtx_decode(processed)
    for r in dmtx_results:
        val = r.data.decode("utf-8", errors="replace")
        if val not in results:
            results.append(val)

    # Try pyzbar if available
    if HAS_ZBAR:
        zbar_results = zbar_decode(processed)
        for r in zbar_results:
            val = r.data.decode("utf-8", errors="replace")
            if val not in results:
                results.append(val)

    return results


app = typer.Typer()


@app.command()
def extract_bubblesheets(
    input_pdf: Annotated[Path, typer.Argument()],
    output_pdf: Annotated[Path, typer.Argument()],
    dpi: Annotated[int, typer.Option()] = 200,
):
    """
    Extract all pages containing a Gradescope bubblesheet.

    Arguments:
        * input_pdf (Path): path to the input file
        * output_pdf (Path): path to the output file

    Returns:
        int: the number of pages found
    """
    reader = PdfReader(input_pdf)
    writer = PdfWriter()
    pdf = PdfDocument(input_pdf)

    for i, page in enumerate(pdf):
        pil_image = page.render(scale=dpi/72).to_pil()
        values = find_datamatrix_values(pil_image)

        if any(v in VALID_CODES for v in values):
            print(f"✅ Page {i+1}: Found {values} — extracted")
            writer.add_page(reader.pages[i])
        else:
            print(f"❌ Page {i+1}: No matching DataMatrix ({values})")

    if writer.pages:
        with open(output_pdf, "wb") as f:
            writer.write(f)
        print(f"\n🎉 Saved extracted pages to: {output_pdf}")
    else:
        print("\n⚠️ No pages with the specified DataMatrix codes were found.")


if __name__ == "__main__":
    app()
