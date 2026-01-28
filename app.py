import streamlit as st
import camelot
import pandas as pd
import pdfplumber
import io
import os
import tempfile

# Set up page branding - This replaces the HTML title and favicon
st.set_page_config(page_title="BBS PDF Convertor", page_icon="📊", layout="wide")

# Custom CSS to keep your professional look without external files
st.markdown("""
    <style>
    .main { background-color: #f8fafc; }
    .stButton>button { width: 100%; border-radius: 8px; background-color: #0d6efd; color: white; height: 3em; border: none; font-weight: bold; }
    .stButton>button:hover { background-color: #0b5ed7; border: none; }
    .header-text { text-align: center; margin-bottom: 2rem; }
    </style>
""", unsafe_allow_html=True)

HEADERS = ["Bar Mark", "Type", "Size", "Total No.", "Shape No.", "a", "b", "c", "d", "e", "f", "g", "h", "i"]
KEY_COLUMNS = ["bar mark", "type", "size", "total no", "shape no"]

def find_start_page(pdf_path):
    """Identifies which page the BBS table starts on."""
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = " ".join(w["text"].lower() for w in page.extract_words(use_text_flow=True))
            if all(col in text for col in KEY_COLUMNS):
                return i + 1
    return None

def extract_tables(uploaded_file):
    """Processes PDF and returns a consolidated DataFrame."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    try:
        start_page = find_start_page(tmp_path)
        if not start_page: return None
        
        # Use Camelot for table extraction
        tables = camelot.read_pdf(tmp_path, pages=f"{start_page}-end", flavor="lattice")
        if tables.n == 0:
            tables = camelot.read_pdf(tmp_path, pages=f"{start_page}-end", flavor="stream")

        all_dfs = []
        for table in tables:
            df = table.df.replace(r"[\r\n]", " ", regex=True)
            # Clean up 'nan' strings that show up in PDF parsing
            df = df.applymap(lambda x: "" if str(x).lower() == "nan" else x)
            all_dfs.append(df)
        
        return pd.concat(all_dfs, ignore_index=True) if all_dfs else None
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# --- STREAMLIT UI ---
st.markdown("<div class='header-text'>", unsafe_allow_html=True)
st.title("📊 BBS PDF Convertor")
st.markdown("Convert BBS PDF to Excel effortlessly. Upload a PDF to automatically extract Bar Marks, Types, and Sizes.")
st.markdown("</div>", unsafe_allow_html=True)

# File Uploader replaces the HTML form
uploaded_file = st.file_uploader("Click to select PDF or drag and drop", type="pdf")

if uploaded_file:
    # Use session state to store the data once it's extracted
    if 'extracted_df' not in st.session_state:
        with st.spinner('Scanning PDF tables... this may take a moment...'):
            st.session_state.extracted_df = extract_tables(uploaded_file)
    
    df = st.session_state.extracted_df
    
    if df is not None:
        st.success("✓ Tables successfully identified!")
        
        # 1. Preview Area
        st.subheader("1. Data Preview")
        display_df = df.copy()
        # Rename columns to indices (0, 1, 2...) for easy mapping
        display_df.columns = [str(i) for i in range(len(df.columns))]
        st.dataframe(display_df, use_container_width=True, height=400)

        # 2. Mapping Area
        st.subheader("2. Map Columns to Standard Format")
        mapping = {}
        # Create a 4-column grid for mapping selections
        m_cols = st.columns(4)
        for i, h in enumerate(HEADERS):
            with m_cols[i % 4]:
                mapping[h] = st.selectbox(
                    f"**{h}**", 
                    options=["Ignore"] + list(range(len(df.columns))), 
                    key=f"map_{h}"
                )

        # 3. Export Action
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Process & Generate Excel"):
            # Build the output dataframe based on mapping
            final_data = {h: (df.iloc[:, m] if m != "Ignore" else "") for h, m in mapping.items()}
            out_df = pd.DataFrame(final_data)
            
            # Save to Excel buffer
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                out_df.to_excel(writer, index=False)
            
            st.session_state.xlsx_ready = output.getvalue()
            st.balloons()

        # Show download button if excel is ready
        if 'xlsx_ready' in st.session_state:
            st.download_button(
                label="📥 Download Corrected File",
                data=st.session_state.xlsx_ready,
                file_name="bbs_extracted_data.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
    else:
        st.error("No valid BBS tables found. Please ensure your PDF has headers like 'Bar Mark' and 'Type'.")

st.markdown("---")
st.caption("Note: Processing happens securely on the Streamlit server.")
