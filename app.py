import streamlit as st
import camelot
import pandas as pd
import pdfplumber
import io
import os
import tempfile

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="BBS PDF Convertor", page_icon="📊", layout="wide")

# Custom CSS for a professional look
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #0d6efd; color: white; height: 3em; border: none; font-weight: bold; }
    .stButton>button:hover { background-color: #0b5ed7; border: none; }
    .header-text { text-align: center; margin-bottom: 2rem; }
    </style>
""", unsafe_allow_html=True)

HEADERS = ["Bar Mark", "Type", "Size", "Total No.", "Shape No.", "a", "b", "c", "d", "e", "f", "g", "h", "i"]
KEY_COLUMNS = ["Bar Mark", "Type", "Size", "Total No.", "Shape No."]

# --- YOUR ORIGINAL LOGIC (PORTED FROM RUN.PY) ---

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
    required_cols = ["Bar Mark", "Type", "Size", "Total No.", "Shape No."]
    required_cols = [c for c in required_cols if c in df.columns]
    if not required_cols:
        return df
    mask = df[required_cols].apply(lambda x: x.astype(str).str.strip() != '').all(axis=1)
    return df[mask]

def extract_tables(uploaded_file):
    # Save uploaded file to a temporary location for Camelot
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        start_page = find_start_page(tmp_path)
        if not start_page: return None

        # Try grid extraction first
        tables = camelot.read_pdf(tmp_path, pages=f"{start_page}-end", flavor="lattice")
        if tables.n == 0:
            tables = camelot.read_pdf(tmp_path, pages=f"{start_page}-end", flavor="stream")

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
            
            if not df.empty: 
                all_tables.append(df)
        
        final_df = pd.concat(all_tables, ignore_index=True, sort=False) if all_tables else None
        return final_df
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# --- STREAMLIT UI ---

st.markdown("<div class='header-text'>", unsafe_allow_html=True)
st.title("📊 BBsS PDF Convertor")
st.markdown("Convert BBS PDF to Excel effortlessly using advanced table detection.")
st.markdown("</div>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload your BBS PDF file", type="pdf")

if uploaded_file:
    # We use session state to remember the data across clicks
    if 'data' not in st.session_state:
        with st.spinner('Scanning pages for tables...'):
            st.session_state.data = extract_tables(uploaded_file)
    
    df = st.session_state.data

    if df is not None and not df.empty:
        st.success(f"✓ Successfully extracted {len(df)} rows of data.")
        
        # 1. Preview Area
        st.subheader("1. Data Preview")
        # Replace 'nan' strings with empty for a clean preview
        display_df = df.replace('nan', '', regex=True)
        st.dataframe(display_df, use_container_width=True, height=400)

        # 2. Mapping Area
        st.subheader("2. Map Columns to Standard Format")
        mapping = {}
        m_cols = st.columns(4)
        for i, h in enumerate(HEADERS):
            with m_cols[i % 4]:
                # Streamlit selectbox for column mapping
                mapping[h] = st.selectbox(
                    f"**{h}**", 
                    options=["(Ignore)"] + list(df.columns), 
                    key=f"map_{h}"
                )

        # 3. Export Area
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Process & Generate Excel"):
            # Build output DataFrame based on user mapping
            final_dict = {}
            for h, mapped_col in mapping.items():
                if mapped_col != "(Ignore)":
                    final_dict[h] = df[mapped_col]
                else:
                    final_dict[h] = ""
            
            out_df = pd.DataFrame(final_dict)
            
            # Save to Excel buffer
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                out_df.to_excel(writer, index=False)
            
            st.session_state.xlsx_output = output.getvalue()
            st.balloons()

        if 'xlsx_output' in st.session_state:
            st.download_button(
                label="📥 Download Excel File",
                data=st.session_state.xlsx_output,
                file_name="bbs_converted_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.error("No valid BBS tables found. Ensure the PDF contains headers like 'Bar Mark' and 'Type'.")

st.markdown("---")
st.caption("This tool is hosted on Streamlit Cloud for long-term free maintenance.")
