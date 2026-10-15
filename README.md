# Prince Masala — Python Framework Project

A Gujarati business management web application using Flask and SQLite.
The original Flutter reference lives beside this folder in `prince_masala`.

## Current progress

Steps 1–6 are complete: Flask setup, responsive dashboard, Gujarati font,
SQLite database, all 277 original products, product management, billing,
pending balances with payment history, and worker salary management.
The dashboard shows the actual product count and today's saved bill count/total.
All four main modules are available. Sales totals remain zero until bills are saved.

Next: the final submission check and screenshots.

## Workers, hours, advances, and salaries

1. Choose **કર્મચારી પગાર** on the dashboard or open `/workers`.
2. Use **કર્મચારી ઉમેરો**, enter the worker's name and hourly rate, then save.
3. Open the worker and choose **કામના કલાક**. Select today or an earlier date
   and enter 0–24 hours with up to two decimal places. For example, 7.5 means
   7 hours 30 minutes; 0 records an absence. Gujarati digits are supported.
4. Only one attendance record is allowed per worker per date. To correct it,
   open the existing month's record and choose **કલાક સુધારો**. Corrections
   preserve that record's original hourly rate.
5. Use **એડવાન્સ** to record a dated advance and its reason. Repeated submissions
   of the same form do not add the advance twice. Incorrect advances can be
   deleted after confirmation; doing so changes that month's salary calculation.
6. Choose a month to see its total hours, gross earnings, advances, and payable
   salary. Earlier/later months' advances are excluded.
7. Use **પગાર પત્રક / પ્રિન્ટ** for a daily attendance table, rates, earnings,
   advance details, payable salary, and signature spaces. Click **પ્રિન્ટ / PDF**
   to print or save through your browser. Physical print output needs a manual check.
8. Worker details/rates can be edited. Existing daily rates remain unchanged;
   the new rate applies when adding new records, including new backdated records.
9. Workers with recorded hours or advances cannot be deleted, preserving history.

Each day's earnings = recorded hours × that day's recorded rate, rounded half-up
to the nearest paise. Monthly gross earnings sum those daily amounts. Payable salary
is gross earnings minus that month's advances, with a minimum payable of zero.
If advances exceed earnings, the excess is shown separately; it is not silently
discarded or automatically carried into another month. This application creates
salary calculations/statements, not salary payment receipts or settlement records.

Example: 100 hours × ₹50 − ₹1,000 advance = ₹4,000 payable salary.

## Pending bills and payments

1. Choose **બાકી બિલ** on the dashboard or open `/pending`.
2. Use **બાકી બિલ ઉમેરો** for a standalone existing outstanding balance.
   Enter the customer, original date and current amount due. This entry does
   not create a new sale or alter dashboard sales totals.
3. For a bill saved in this app, open its invoice and choose
   **આ સંપૂર્ણ બિલ બાકી તરીકે ઉમેરો**. This links the full invoice amount once.
   If the customer already paid part of that bill, record that payment next.
4. Open **વિગતો / ચુકવણી**, enter the amount received and payment date,
   then choose **ચુકવણી સાચવો**. Gujarati and English digits are supported.
5. Each payment reduces the outstanding balance. Overpayments, zero/negative
   amounts, payment dates before the bill or after today, and duplicate
   submissions are rejected or safely reused.
6. When the balance reaches zero, the payment form closes and the record
   moves to the **ચૂકવેલાં** filter. Choose **બધાં** to see all records.
7. Search by customer name or linked bill number. The highlighted total always
   shows the entire ledger's outstanding balance, regardless of the filter.
8. Standalone entries can be edited. Their original amount cannot be reduced
   below recorded payments. Linked invoice names, dates and amounts remain fixed.
9. Entries without payments can be deleted after confirmation. Entries with
   payment history are retained. A ledger deletion never deletes the invoice.

Payments do not change sales totals or create additional bills. A schema update
adds duplicate-payment protection without removing existing database records.
Payment reversal/correction is not part of this step; verify the amount and
date before recording a payment.

## Create and print a bill

1. Choose **નવું બિલ** on the dashboard or visit `/bills/new`.
2. Enter the customer's name and check the bill date.
3. Search for a product in Gujarati or English, then select a search result.
4. Enter a whole-number quantity and selling price. The catalogue's reference
   price is shown for guidance; it is deliberately not copied into the selling price.
5. Click **બિલમાં ઉમેરો**. Repeat for other products. The total updates immediately.
6. Use **સુધારો** or **કાઢો** in the bill list to adjust items before saving.
7. Click **બિલ સાચવો અને જુઓ** to save the complete bill with a unique number.
8. Click **પ્રિન્ટ / PDF**. Select a printer or **Save as PDF** in the browser's
   print dialog. Use A4 paper; turn browser headers/footers off if unwanted.
9. Visit **બિલ યાદી** (`/bills`) to search saved bills by customer or bill number
   and open them for reprinting.

The bill builder requires JavaScript. It accepts Gujarati and English digits.
Drafts are kept in this browser tab's session storage when available, including
across refreshes; this is not a saved bill or a substitute for clicking Save.
A completed draft is cleared when its saved invoice opens. Closing the tab can
discard an unsaved draft. The app warns before leaving an unfinished bill.

Bills are saved atomically with item names and selling prices at the time of sale.
Editing or deleting a catalogue item does not change a saved invoice. Repeated
submissions of the same bill form return the existing bill, including concurrent
retries. Opening or printing bills never increments sales totals.

The print stylesheet hides navigation and controls, repeats table headers, and
supports longer invoices across pages. Physical printer output needs a manual
check with your chosen printer/browser. This is a simple business bill; no GST
registration details or tax calculations have been supplied or added.

## Use the product catalogue

1. Open the dashboard, then choose **વસ્તુઓ** or visit `/items`.
2. Search by Gujarati or English name. Search ignores English capitalization
   and matches any part of a name. Use **બધી વસ્તુઓ** to clear the search.
3. Use **વસ્તુ ઉમેરો** to add a Gujarati name, English search name and reference price.
4. Use **સુધારો** to edit a product. Prices accept English or Gujarati digits,
   with up to two decimal places; billing selling prices will be entered separately.
5. Use **કાઢો** to open the deletion confirmation, then confirm or cancel.
6. Browse 30 products per page using the previous/next buttons.

All form changes are saved to SQLite. Form tokens protect against unwanted
cross-site submissions; the local session key lives in the ignored `instance` folder.

## Database

The database is automatically created at `instance/prince_masala.sqlite3` on
first launch. Initial products are bundled in `data/initial_items.json`, so
the Python project runs independently of the original Flutter folder.

- `items`: Gujarati names, English search terms, and reference prices.
- `bills` and `bill_items`: completed bills and original item names and selling rates.
- `bill_submissions`: prevents saving the same submitted bill twice.
- `pending_actions`: prevents duplicate pending-entry/payment submissions.
- `worker_actions`: prevents duplicate worker/advance submissions.
- `pending_bills` and `pending_payments`: outstanding amounts and payment history.
- `workers`, `worker_hours`, `worker_advances`: rates, dated hours, and advances.
- `app_metadata`: records the one-time product import.

Amounts are stored as integer paise (₹60 = 6000 paise) to avoid floating-point
errors in money. Dates will use `YYYY-MM-DD`. Worker-hour records retain their
hourly rate so future rate edits need not change previous earnings.
Sales summaries will be calculated from saved bills rather than print actions.

Restarting does not duplicate products, overwrite price changes, or restore
deleted products. A catalogue deliberately emptied after import stays empty.
No customer, bill, worker, or salary records have been invented.

To check initialization manually from the project folder with the environment active:

```bash
python -m flask --app app init-db
```

This command preserves existing data. Keep a backup of the `instance` folder
when moving this project to another computer; the initial product list does
not include your later business records.

## Verify the database

From the project folder with the environment active:

```bash
python -m unittest discover -s tests -v
```

Checks cover the 277 products, persistence, repeat initialization, deleted items,
invalid values, duplicate daily hours, bill calculations, repeated/concurrent saves,
bill history, schema upgrades, and preservation of bill item details.
Tests use temporary databases for business record changes.

## Run on this computer

Use the existing virtual environment in the parent workspace:

```bash
cd /Users/krishsondagar/Desktop/prince_python_framwork
source .venv/bin/activate
cd prince_masala_python
python app.py
```

Open http://127.0.0.1:5001 in your browser. Stop the server with Ctrl+C.
Port 5001 avoids the common macOS conflict on port 5000.

## Set up on another computer

From inside this project folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

On Windows, activate with `.venv\Scripts\activate` instead.

## Preview on a phone

Keep your phone and computer on the same trusted Wi-Fi. From this project folder,
with the virtual environment activated, run:

```bash
python -m flask --app app run --host=0.0.0.0 --port=5001
```

Open `http://YOUR_COMPUTER_LAN_IP:5001` on the phone, replacing the placeholder
with the computer's Wi-Fi IP address. The computer must remain running.
This is a local development preview; internet hosting is a separate step.

## Structure

```text
app.py                  Flask application and routes
products.py             Catalogue search, add, edit and delete routes
billing.py              Bill validation, saving, history and invoice routes
pending.py              Outstanding balances and partial/full payment recording
salary.py               Workers, daily attendance, advances and monthly statements
money.py                Exact rupee input and Gujarati digit support
database.py             Database connections and one-time initialization
schema.sql              Version 1 database tables and constraints
migration_2.sql         Non-destructive duplicate-submission support
migration_3.sql         Non-destructive pending-payment submission protection
migration_4.sql         Non-destructive worker/advance submission protection
data/initial_items.json  All 277 original products with prices in paise
tests/test_database.py  Database checks
templates/base.html     Shared page layout
templates/home.html     First welcome page
static/css/style.css    Responsive styling
static/fonts/           Gujarati font from the Flutter project
instance/               Local database location (created at runtime)
requirements.txt        Python dependencies
```

## Submission and demonstration

For a fresh computer, follow `INSTALL.md`. For disposable demonstration data, run
`python demo_preview.py` and open http://127.0.0.1:5002. Demo data is temporary
and does not replace real business records. The submission documentation describes
this implementation as Flask with direct SQL; authentication is intentionally omitted.
