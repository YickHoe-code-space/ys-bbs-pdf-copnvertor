from flask import Flask, render_template, request, redirect, url_for, send_file
import camelot
import pandas as pd
import pdfplumber
import io
app = Flask(__name__)

HEADERS = ["Bar Mark", "Type", "Size", "Total No.", "Shape No.", "a","b","c","d","e","f","g","h","i"]
KEY_COLUMNS = ["Bar Mark", "Type", "Size", "Total No.", "Shape No."]

def find_start_page(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = " ".join(w["text"].lower() for w in page.extract_words(use_text_flow=True))
            if "bar" in text and "mark" in text:
                return i + 1
    return None

def find_header_row(df):
    for idx, row in df.iterrows():
        row_text = " ".join(row.astype(str).str.lower())
        if "bar mark" in row_text and ("shape code" in row_text or "shape no" in row_text):
            return idx
    return None

def remove_sparse_rows(df, threshold=0.5):
    n_cols = len(df.columns)
    mask = df.apply(lambda row: (row.fillna('').astype(str).str.strip() != '').sum() / n_cols > (1 - threshold), axis=1)
    return df[mask]

def make_columns_unique(cols):
    seen = {}
    new_cols = []
    for c in cols:
        c = str(c).strip()
        new_cols.append(f"{c}_{seen[c]+1}" if c in seen else c)
        seen[c] = seen.get(c, 0) + 1
    return new_cols

def clean_dataframe(df):
    df = df.dropna(axis=1, how='all')
    for col in df.select_dtypes(include="object"):
        df[col] = df[col].astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()
    return df

def filter_key_rows(df):
    # Only consider these required columns
    required_cols = ["Bar Mark", "Type", "Size", "Total No.", "Shape No."]
    # Keep only columns that actually exist in the DataFrame
    required_cols = [c for c in required_cols if c in df.columns]
    if not required_cols:
        return df
    # Keep rows where all required columns are non-empty
    mask = df[required_cols].apply(lambda x: x.astype(str).str.strip() != '').all(axis=1)
    return df[mask]

def extract_tables(pdf_path):
    start_page = find_start_page(pdf_path)
    if not start_page: return pd.DataFrame()

    tables = camelot.read_pdf(pdf_path, pages=f"{start_page}-end", flavor="lattice")
    if tables.n == 0:
        tables = camelot.read_pdf(pdf_path, pages=f"{start_page}-end", flavor="stream")

    all_tables = []
    current_headers = None

    for table in tables:
        df = table.df.replace("\n", " ", regex=True)
        header_idx = find_header_row(df)
        if header_idx is not None:
            current_headers = df.iloc[header_idx].str.strip()
            df = df.iloc[header_idx+1:].copy()
        if current_headers is not None and len(df.columns) == len(current_headers):
            df.columns = current_headers
        df.columns = make_columns_unique(df.columns)
        df = clean_dataframe(df)
        df = filter_key_rows(df)
        df = remove_sparse_rows(df, threshold=0.5)
        if "Bar Mark" in df.columns:
            df = df[df["Bar Mark"].astype(str).str.strip() != '']
        if not df.empty: all_tables.append(df)
    return pd.concat(all_tables, ignore_index=True, sort=False) if all_tables else pd.DataFrame()
@app.route("/", methods=["GET","POST"])
def upload():
    if request.method == "POST":
        pdf = request.files["pdf"]
        extract_tables(pdf).to_pickle("temp.pkl")
        return redirect(url_for("preview"))
    return render_template("upload.html")
@app.route("/preview", methods=["GET","POST"])
def preview():
    df = pd.read_pickle("temp.pkl")
    tables = clean_dataframe(df).to_html(classes="table table-bordered", index=False)
    if request.method == "POST":
        mapping = {h: request.form.get(h) for h in HEADERS}
        out = pd.DataFrame({h: df[src] if src else "" for h, src in mapping.items()})
        output = io.BytesIO()
        out.to_excel(output, index=False)
        output.seek(0)
        return send_file(output, download_name="fixed_output.xlsx", as_attachment=True)
    return render_template("preview.html", tables=tables, columns=df.columns, headers=HEADERS)

if __name__ == "__main__":
    app.run(debug=True)