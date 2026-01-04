# Kindle Paper Converter

A powerful automated tool to convert academic papers (PDFs) into a Kindle-friendly format. It optimizes two-column PDFs, generates cover images for better library visualization, and automatically emails the converted file to your Kindle.

## Features

- **Smart Layout Detection**: Automatically detects if a paper uses a two-column layout and adjusts conversion settings accordingly.
- **Cover Generation**: Creates a cover page from the first page of the PDF so it looks good in your Kindle library.
- **Kindle Optimization**: Uses `k2pdfopt` with tuned settings for maximum readability on E-ink screens (contrast enhancement, margin removal, smart text reflow).
- **Auto-Delivery**: Emails the converted file directly to your Kindle email address using SMTP.
- **Archiving**: Automatically moves processed files to an archive folder.

## Prerequisites

- Python 3.x
- `k2pdfopt` executable in the project root.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <repository-url>
    cd kindle_paper_converter
    ```

2.  **Install Python dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Setup `k2pdfopt`**:
    Download the `k2pdfopt` executable for your OS (macOS/Linux) and place it in the root folder of this project. Ensure it is named `k2pdfopt` and is executable:
    ```bash
    chmod +x k2pdfopt
    ```

4.  **Configure Environment**:
    Create a `.env` file based on the example:
    ```bash
    cp .env.example .env
    ```
    Edit `.env` with your email credentials and Kindle email address:
    ```
    EMAIL_USER=your_email@example.com
    EMAIL_PASS=your_password
    KINDLE_EMAIL=your_kindle_email@kindle.com
    ```

## Usage

1.  Place your raw PDF papers into the `papers_orig` folder.
2.  Run the converter script:
    ```bash
    python kindle_paper_pro.py
    ```
3.  The script will:
    - Detect the layout.
    - Generate a cover.
    - Convert the PDF.
    - Email it to your Kindle.
    - Move the original file to `papers_archive`.

## Output

Converted files are saved temporarily in `papers_kindle` before being emailed.
