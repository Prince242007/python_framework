# Install and demonstrate Prince Masala

This project uses Flask, not Django. No authentication is included.

## Fresh setup

Open a terminal inside this project folder. Python 3.10 or newer is recommended; the verified environment is Python 3.14.7.

### macOS or Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

### Windows

```bat
py -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m pip install tzdata
python app.py
```

Open http://127.0.0.1:5001. The `instance` folder and database are created automatically. The first launch imports 277 products. Stop the server with Ctrl+C.

If timezone data is unavailable on another operating system, install it with `python -m pip install tzdata`.

## Run tests

From the project folder with the environment activated:

```bash
python -m unittest discover -s tests -v
```

Expected result for this submission: 41 tests, all passing. The automated tests use temporary databases for business-record changes.

## Practice with disposable records

```bash
python demo_preview.py
```

Open http://127.0.0.1:5002. This creates demo invoices, a pending balance, a worker, hours and an advance in a temporary database. These records are removed when the demo ends and do not replace the real database.

## Use a phone on the same Wi-Fi

```bash
python -m flask --app app run --host=0.0.0.0 --port=5001
```

Open `http://YOUR_COMPUTER_LAN_IP:5001` on your phone. Replace the placeholder with your computer's Wi-Fi IP address. Keep the computer running. This is a trusted local demonstration setup, not a public deployment.

## Preserve business records

Keep a backup of the complete `instance` folder before moving the app. Do not publish that folder to GitHub. It contains your database and local session key. Source installation starts with products only; it does not include your personal customer, worker or payment data.

## Printing

Open a saved bill or salary statement and choose Print/PDF. Select A4 and a printer or Save as PDF. Physical printer output needs your manual check.
