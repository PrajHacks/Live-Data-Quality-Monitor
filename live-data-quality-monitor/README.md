# live-data-quality-monitor

Starter project for pulling live product data from the Open Food Facts API and shaping it into a clean Pandas DataFrame.

## What it does

- Uses the current structured Open Food Facts search API at `/api/v2/search`
- Splits the pull into several beverage batches filtered by country so it can stay under the anonymous per-query result ceiling
- Deduplicates by barcode and keeps only the fields needed for downstream validation
- Fetches at least 2,000 unique products when available
- Flattens the product payload into a tabular CSV-friendly structure
- Saves both a timestamped file and a `products_latest.csv` copy under `data/incoming/`
- Prints a quick data-quality summary with missing-value percentages per column

## Setup

```bash
pip install -r requirements.txt
```

Create a `.env` file in the project root with your MySQL credentials:

```env
MYSQL_HOST=localhost
MYSQL_USER=root
MYSQL_PASSWORD=changeme
MYSQL_DATABASE=data_quality_monitor
```

If you want to email the reports from the Streamlit app, add these settings too:

```env
EMAIL_ADDRESS=your_email@example.com
EMAIL_PASSWORD=your_email_password_or_app_password
SMTP_SERVER=smtp.example.com
SMTP_PORT=587
```

If you deploy the app on Streamlit Cloud, put the email settings in Streamlit's
`st.secrets` manager instead of committing them to a `.env` file.

## Run

```bash
python scripts/fetch_live_data.py
```

## Validate

Run the validation summary against `data/incoming/products_latest.csv` and generate the Excel report:

```bash
python scripts/setup_database.py
python src/validator.py
```

Run `scripts/setup_database.py` once to create the `runs` and `issues` tables, then run
`src/validator.py` normally to save each validation run and its issue details to MySQL.

## Streamlit App

Launch the local web app to fetch live data or upload your own CSV:

```bash
streamlit run app/streamlit_app.py
```

The app shows the overall quality score, the four sub-scores, issue charts, a detailed
issue table, buttons to download the generated Excel and PDF reports, and an email form
for sending both files to a stakeholder.

## Output

- `data/incoming/products_YYYY-MM-DD.csv`
- `data/incoming/products_latest.csv`
- `reports/Data_Quality_Report_YYYY-MM-DD_HHMM.xlsx`

The script is intentionally modular so a validation layer can be added on top of the resulting DataFrame in the next milestone.
