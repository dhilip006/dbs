# Smart Xerox Portal (MVP)

A starter Flask application for a student PDF-to-Xerox workflow.

## Included
- Student upload without student login (40 MB limit)
- Accepts PDF, images (JPG, PNG, WEBP, GIF, BMP, TIFF) and Word files (DOC, DOCX, ODT, RTF, TXT); everything is converted to PDF automatically
- Name capture (no mobile number is collected)
- Page selection using ranges, e.g. `1-5, 8, 10-12`
- Copies, B&W/colour, single/double-sided, A4/A3 options
- 1, 2, 4, 6 or 8 pages per sheet (N-up PDF generation)
- Estimate calculation
- Demo payment step (does NOT charge money)
- Order tracking page
- Password-protected shop dashboard
- Print-to-default-printer action from the computer running Flask

## Run on Windows
1. Install Python 3.10 or newer.
2. Extract this ZIP.
3. Open Command Prompt in this folder.
4. Run:
   ```bat
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
5. Open `http://127.0.0.1:5000`.

## Admin
- Open `http://127.0.0.1:5000/admin`
- Prototype password: `admin123`
- Change it before use by setting environment variable `ADMIN_PASSWORD`.

## Printer connection
The print action runs on the machine hosting this Flask app and sends the processed PDF to the OS default printer:
- Windows: invokes the default PDF application's print action.
- Linux: uses the `lp` command.

Install the printer driver, set the printer as the operating system's default printer, and test printing locally first. Some PDF reader applications may open a dialog rather than print silently. A production system should use a dedicated local print agent and a secure authenticated job-pull channel, especially when the website is hosted in the cloud.

## IMPORTANT: before public launch
This is a development MVP, not a production-ready high-traffic/payment system.

- The demo payment button is not a real payment gateway. Integrate Razorpay/Cashfree (or another supported provider), verify payment signatures/webhooks on the server, and only release paid jobs after verified payment.
- Do not expose Flask's development server to the public internet. Deploy behind a production WSGI server, HTTPS reverse proxy, rate limiting, monitoring and backups.
- Replace the simple admin password flow with proper hashed credentials, sessions, CSRF protection and role-based access.
- Use private object storage, signed URLs, malware scanning, file retention/deletion rules and encrypted transport.
- Add a durable job queue (e.g. Redis + Celery/RQ), database (e.g. PostgreSQL), worker processes, load testing and autoscaling for high concurrent traffic.
- Add printer-specific status/toner/paper monitoring only where supported by the printer model and protocol.
- Pricing formula here is only a demo estimate; confirm exact shop pricing and double-side/N-up rules.
- Set `SECRET_KEY`, `ADMIN_PASSWORD`, `BW_RATE`, and `COLOR_RATE` as environment variables.
- Uploaded documents may contain personal data. Restrict access and delete files according to a clear retention policy.

## Notes
- Word files are converted with **LibreOffice** (free, https://www.libreoffice.org) installed on the shop PC; on Windows, Microsoft Word + `pip install docx2pdf` also works as a fallback. PDFs and images need no extra software.
- UI theme: dark God of War style with 3D tilt cards, a rotating cube, ember particles and animations. Fonts are bundled in `static/fonts` (Cinzel / Cinzel Decorative, the closest open fonts to the game's title lettering). To use a different God of War-style font (e.g. the free 'Norse' font), drop `GodOfWar.woff2` or `GodOfWar.ttf` into `static/fonts/`; it is picked up automatically.
- Older databases that stored a phone number are migrated automatically on first start (the phone column is dropped).
- The print button uses the default printer on the server/shop PC. A remote cloud deployment needs a local print agent installed at each shop.
