"""
This module is for finding and extracting the pages of a PDF file that
are Gradescope bubble sheets. It's my second attempt.

It doesn't work, and it might not be necessary. Gradescope splits the PDF
at each bubblesheet (which I knew how it recognized them), and allows you
to create the submissions in a batch.
"""

from pdf2image import convert_from_path
from PyPDF2 import PdfReader, PdfWriter
import cv2
import numpy as np
from pathlib import Path

import typer
from typing import Annotated

import sys
from loguru import logger
logger.remove()
logger.add(sys.stderr, level="DEBUG")


# --- Settings ---
pdf_path = "scanned_exams.pdf"
template_path = "bubble_sheet_template.pdf"
output_pdf = "bubble_sheet_pages.pdf"
dpi = 200  # resolution for image conversion
corner_inch = 2  # size of corner region to check
similarity_threshold = 0.85  # adjust as needed

# --- Helper functions ---
def mse(imageA, imageB):
    """Mean Squared Error between two images"""
    err = np.sum((imageA.astype("float") - imageB.astype("float")) ** 2)
    err /= float(imageA.shape[0] * imageA.shape[1])
    return err

def compare_patch(page_patch, template_patch):
    """Return similarity score (1 = perfect match)"""
    page_gray = cv2.cvtColor(page_patch, cv2.COLOR_BGR2GRAY)
    template_gray = cv2.cvtColor(template_patch, cv2.COLOR_BGR2GRAY)
    # Resize page_patch to template_patch in case of small variations
    page_resized = cv2.resize(page_gray, (template_gray.shape[1], template_gray.shape[0]))
    score = 1 / (1 + mse(page_resized, template_gray))  # convert MSE to similarity
    logger.debug(f"compare_patch.result: {score}")
    return score

# --- Load PDFs and convert to images ---
def extract_matching_pages(
        pdf_path: Annotated[Path, typer.Argument()],
        template_path: Annotated[Path, typer.Argument()],
        output_pdf: Annotated[Path, typer.Argument()],
        dpi: Annotated[int, typer.Option()] = 200
    ):
    """
    Find all pages of pdf_path which match template_path
    and extract to output_pdf.
    """

    pages = convert_from_path(pdf_path, dpi=dpi)
    template_pages = convert_from_path(template_path, dpi=dpi)
    template_img = np.array(template_pages[0])  # assuming single-page template
    
    # Calculate corner region in pixels
    corner_px = int(dpi * corner_inch)

    # Extract template corners
    tpl_h, tpl_w, _ = template_img.shape
    template_corners = [
        template_img[0:corner_px, 0:corner_px],  # top-left
        template_img[0:corner_px, tpl_w-corner_px:tpl_w],  # top-right
        template_img[tpl_h-corner_px:tpl_h, 0:corner_px],  # bottom-left
        template_img[tpl_h-corner_px:tpl_h, tpl_w-corner_px:tpl_w],  # bottom-right
    ]

    # --- Check each page ---
    matching_pages = []

    for i, page in enumerate(pages):
        logger.debug(f"Checking page {i}")
        page_img = np.array(page)
        ph, pw, _ = page_img.shape
        page_corners = [
            page_img[0:corner_px, 0:corner_px],
            page_img[0:corner_px, pw-corner_px:pw],
            page_img[ph-corner_px:ph, 0:corner_px],
            page_img[ph-corner_px:ph, pw-corner_px:pw],
        ]
        
        scores = [compare_patch(pc, tc) for pc, tc in zip(page_corners, template_corners)]
        
        if all(s >= similarity_threshold for s in scores):
            matching_pages.append(i)

    print(f"Found {len(matching_pages)} matching pages: {matching_pages}")

    # --- Extract matching pages to new PDF ---
    reader = PdfReader(pdf_path)
    writer = PdfWriter()
    for idx in matching_pages:
        writer.add_page(reader.pages[idx])

    with open(output_pdf, "wb") as f_out:
        writer.write(f_out)

    print(f"Matching pages saved to {output_pdf}")


app = typer.Typer()


@app.command()
def extract_bubblesheets(
    input_pdf: Annotated[Path, typer.Argument()],
    output_pdf: Annotated[Path, typer.Argument()],
    dpi: Annotated[int, typer.Option()] = 200,) -> None:
    """
    Extract all pages containing a Gradescope bubblesheet.

    Arguments:
        * input_pdf (Path): path to the input file
        * output_pdf (Path): path to the output file

    Returns: None
    """
    template = Path(__file__).parent / 'mc_bubble_sheet_A.pdf'
    return extract_matching_pages(
        input_pdf,
        template,
        output_pdf
    )
    
if __name__ == "__main__":
    app()
