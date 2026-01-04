import os
import sys
import subprocess
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from pathlib import Path

from dotenv import load_dotenv
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar
import fitz  # PyMuPDF

# --- Configuration & Setup ---
load_dotenv()

# Directories
BASE_DIR = Path(__file__).parent.resolve()
PAPERS_ORIG_DIR = BASE_DIR / "papers_orig"
PAPERS_KINDLE_DIR = BASE_DIR / "papers_kindle"
PAPERS_ARCHIVE_DIR = BASE_DIR / "papers_archive" # New archive directory
K2PDFOPT_PATH = BASE_DIR / "k2pdfopt"

# Email Settings
EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")
KINDLE_EMAIL = os.getenv("KINDLE_EMAIL")

# Limits
MAX_EMAIL_SIZE_MB = 24

# Setup Logging
class EmojiFormatter(logging.Formatter):
    def format(self, record):
        msg = super().format(record)
        if record.levelno == logging.INFO:
            return f"ℹ️  {msg}"
        elif record.levelno == logging.WARNING:
            return f"⚠️  {msg}"
        elif record.levelno == logging.ERROR:
            return f"❌ {msg}"
        elif record.levelno == logging.DEBUG:
            return f"🐛 {msg}"
        return msg

handler = logging.StreamHandler()
handler.setFormatter(EmojiFormatter("%(message)s"))
logger = logging.getLogger("KindlePaperPro")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# --- 1. Layout Detection ---
def detect_layout(pdf_path: Path) -> bool:
    """
    Analyzes the first page layout to detect if it's 2-column.
    Returns True if 2-column layout is detected, False otherwise.
    """
    logger.info(f"🔍 Detectando layout para: {pdf_path.name}")
    try:
        # Analyze only the first page
        for page_layout in extract_pages(pdf_path, page_numbers=[0]):
            page_width = page_layout.width
            right_boundary = page_width * 0.55
            
            # Check for text blocks starting in the right 45% of the page
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    if element.x0 > right_boundary:
                        # Found significant text on the right side
                        # Filter out page numbers or headers if possible, but basic check is usually enough
                        if len(element.get_text().strip()) > 50: # Arbitrary threshold for "significant" text
                             logger.info("   -> Detectado layout de 2 columnas")
                             return True
            
            logger.info("   -> Detectado layout de 1 columna (o no concluyente)")
            return False
        return False # Fallback if empty
        
    except Exception as e:
        logger.warning(f"   -> Error en detección: {e}. Asumiendo 1 columna.")
        return False

# --- 1.5 Cover Generation ---
def generate_cover_page(pdf_path: Path) -> Path:
    """
    Generates a PDF cover page from the first page of the original PDF.
    Renders the first page as an image and saves it as a new PDF.
    """
    logger.info(f"🖼️  Generando portada para: {pdf_path.name}")
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(0)  # First page
        
        # Render page to an image (pixmap)
        # zoom=2 for better resolution (approx 150 dpi which is good for Kindle)
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)
        
        # Create a new PDF for the cover
        cover_pdf_path = PAPERS_KINDLE_DIR / f"{pdf_path.stem}_cover_temp.pdf"
        cover_doc = fitz.open()
        cover_page = cover_doc.new_page(width=pix.width, height=pix.height)
        
        # Insert the image into the new PDF page
        cover_page.insert_image(cover_page.rect, stream=pix.tobytes(), keep_proportion=True)
        
        cover_doc.save(cover_pdf_path)
        cover_doc.close()
        doc.close()
        
        logger.info("   -> Portada generada exitosamente.")
        return cover_pdf_path
        
    except Exception as e:
        logger.error(f"   -> Falló la generación de portada: {e}")
        return None

# --- 2. Conversion Engine ---
def convert_paper(pdf_path: Path, is_two_column: bool) -> Path:
    """
    Converts the PDF using k2pdfopt with optimized settings.
    Returns the path to the converted file.
    """
    logger.info(f"⚙️  Procesando: {pdf_path.name}...")
    
    # Create a safe output filename
    # Truncate original name to avoid issues and remove spaces for safety
    safe_stem = "".join(c for c in pdf_path.stem if c.isalnum() or c in (' ', '-', '_')).strip()
    safe_stem = safe_stem.replace(" ", "_")
    if len(safe_stem) > 50:
         safe_stem = safe_stem[:50]
         
    output_filename = f"{safe_stem}_k2opt.pdf"
    output_path = PAPERS_KINDLE_DIR / output_filename
    
    # Base command (VERSIÓN NEUROCIENCIA PRO)
    cmd = [
        str(K2PDFOPT_PATH),
        "-dev", "kpw",      # Kindle Paperwhite size
        "-ui-",             # No UI
        "-x",               # Exit on finish
        
        # --- MEJORAS VISUALES ---
        "-n",               # <--- CRÍTICO: Mantiene resolución nativa de imágenes (No pixela gráficos)
        "-jpg", "92",       # Subimos calidad JPG a 92 (antes 85) para menos artefactos
        "-wt", "-1",        # Auto-blanqueado inteligente del fondo
        "-cmax", "1",       # Contraste máximo para texto nítido
        "-om", "0.05",      # Márgenes mínimos (casi cero) para maximizar tamaño
        
        # --- AJUSTES DE LECTURA ---
        "-ws", "0.1",       # Word spacing un poco más estricto para evitar saltos raros
        "-g", "0.5",        # Gamma 0.5 (engrosa un poco la letra fina típica de papers)
        
        "-o", str(output_path) # Output path
    ]
    
    # Mode selection
    if is_two_column:
        cmd.extend(["-mode", "2col"])
    else:
        cmd.extend(["-mode", "fw"]) # Fit width
        
    cmd.append(str(pdf_path))
    
    try:
        # --- Generate Cover First ---
        cover_path = generate_cover_page(pdf_path)
        
        # --- Run k2pdfopt ---
        # Rename output for k2pdfopt to be a temp file
        body_output_filename = f"{safe_stem}_body_temp.pdf"
        body_output_path = PAPERS_KINDLE_DIR / body_output_filename
        
        # Ensure k2pdfopt is executable
        if not os.access(K2PDFOPT_PATH, os.X_OK):
             logger.warning("   -> k2pdfopt no es ejecutable. Intentando chmod +x...")
             os.chmod(K2PDFOPT_PATH, 0o755)

        # Update command output path
        cmd_index = cmd.index("-o") + 1
        cmd[cmd_index] = str(body_output_path)

        logger.debug(f"   Running command: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        
        if not body_output_path.exists():
            if result.returncode != 0:
                logger.error(f"   -> Falló la conversión. Log:\n{result.stdout}")
                raise RuntimeError("k2pdfopt failed")
            logger.error("   -> El archivo de salida de cuerpo no se creó.")
            raise FileNotFoundError(f"Output file not found: {body_output_path}")

        # --- Merge Cover + Body ---
        logger.info("   🔗 Fusionando portada y contenido...")
        final_doc = fitz.open()
        
        if cover_path and cover_path.exists():
            final_doc.insert_pdf(fitz.open(cover_path))
        
        final_doc.insert_pdf(fitz.open(body_output_path))
        
        final_doc.save(output_path)
        final_doc.close()
        
        # Cleanup temps
        if cover_path and cover_path.exists():
            os.remove(cover_path)
        if body_output_path.exists():
            os.remove(body_output_path)

        file_size_mb = output_path.stat().st_size / (1024 * 1024)
        logger.info(f"   ✅ Conversión exitosa (con portada): {output_filename} ({file_size_mb:.2f} MB)")
        return output_path

    except Exception as e:
        logger.error(f"   -> Error crítico en conversión: {e}")
        # Cleanup attempts
        try:
             if 'cover_path' in locals() and cover_path and cover_path.exists(): os.remove(cover_path)
             if 'body_output_path' in locals() and body_output_path.exists(): os.remove(body_output_path)
        except: pass
        raise

# --- 3. Delivery System ---
def send_to_kindle(file_path: Path) -> bool:
    """
    Sends the PDF file to the Kindle email address via Hostinger SMTP.
    Returns True if sent successfully, False otherwise.
    """
    logger.info(f"🚀 Enviando a Kindle: {file_path.name}")
    
    filesize_mb = file_path.stat().st_size / (1024 * 1024)
    if filesize_mb > MAX_EMAIL_SIZE_MB:
        logger.warning(f"   ⚠️  Archivo demasiado grande ({filesize_mb:.2f} MB > {MAX_EMAIL_SIZE_MB} MB). No se enviará.")
        logger.info("   -> Guardado localmente en papers_kindle.")
        return False

    if not all([EMAIL_USER, EMAIL_PASS, KINDLE_EMAIL]):
        logger.warning("   ⚠️  Faltan credenciales de email. Configura el archivo .env.")
        return False

    msg = MIMEMultipart()
    msg['From'] = EMAIL_USER
    msg['To'] = KINDLE_EMAIL
    msg['Subject'] = "Convertido: " + file_path.stem

    body = "Tu paper convertido adjunto."
    msg.attach(MIMEText(body, 'plain'))

    try:
        with open(file_path, "rb") as attachment:
            part = MIMEBase('application', 'pdf')
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f'attachment; filename="{file_path.name}"',
        )
        msg.attach(part)

        text = msg.as_string()
        
        # Connect to Hostinger SMTP Server (SSL)
        with smtplib.SMTP_SSL('smtp.hostinger.com', 465) as server:
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, KINDLE_EMAIL, text)
            
        logger.info("   ✅ Email enviado correctamente.")
        return True
        
    except Exception as e:
        logger.error(f"   ❌ Error al enviar email: {e}")
        return False

# --- 4. Archiving ---
def archive_paper(pdf_path: Path):
    """Moves the successfully processed PDF to the archive folder."""
    try:
        if not PAPERS_ARCHIVE_DIR.exists():
            PAPERS_ARCHIVE_DIR.mkdir(parents=True)
            
        destination = PAPERS_ARCHIVE_DIR / pdf_path.name
        
        # Handle duplicate names in archive
        if destination.exists():
             import time
             timestamp = int(time.time())
             destination = PAPERS_ARCHIVE_DIR / f"{pdf_path.stem}_{timestamp}{pdf_path.suffix}"
             
        pdf_path.rename(destination)
        logger.info(f"   📦 Archivado: {pdf_path.name} -> papers_archive/")
        
    except Exception as e:
        logger.error(f"   ⚠️  Error al archivar: {e}")

# --- Main CLI Flow ---
def main():
    if not PAPERS_ORIG_DIR.exists():
        logger.error(f"Directorio no encontrado: {PAPERS_ORIG_DIR}")
        return
        
    PAPERS_KINDLE_DIR.mkdir(parents=True, exist_ok=True)
    PAPERS_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n📚 Kindle Paper Pro - Iniciando...\n")
    
    pdfs = list(PAPERS_ORIG_DIR.glob("*.pdf"))
    if not pdfs:
        logger.info("No hay PDFs en papers_orig para procesar.")
        return

    for pdf in pdfs:
        try:
            # Layout Detection
            is_2col = detect_layout(pdf)
            
            # Conversion
            output_file = convert_paper(pdf, is_2col)
            
            # Delivery
            sent_success = send_to_kindle(output_file)
            
            # Archive if sent successfully (or if user decides conversion is enough logic)
            # In this robust CLI, we generally assume if conversion worked and we tried to send
            # (or warned about size), we are done with the original.
            # But let's be strict: Only archive if Delivery was OK or Skipped due to Size.
            # If Config is missing, do NOT archive, so user can try again easily.
            
            if sent_success:
                archive_paper(pdf)
            elif output_file.stat().st_size / (1024 * 1024) > MAX_EMAIL_SIZE_MB:
                 # Too big to send, but converted. Archive it.
                 logger.info("   -> Archivado aunque no se envió (Tamaño > Límite).")
                 archive_paper(pdf)
            
            print("-" * 50)
            
        except Exception as e:
            logger.error(f"Falló el proceso para {pdf.name}: {e}")
            print("-" * 50)
            continue
            
    print("\n✨ Proceso completado.\n")

if __name__ == "__main__":
    main()
