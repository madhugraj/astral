import streamlit as st
import os
import pandas as pd
from google import generativeai as genai
import json
import tempfile

# Available fields for extraction
AVAILABLE_FIELDS = {
    "company_name": "Name of the Company (e.g., 'Company', 'Vendor', 'Organization')",
    "invoice_number": "Invoice Number (e.g., 'Invoice No.', 'Bill Number', 'Invoice ID')",
    "total_amount": "Total Amount (e.g., 'Total', 'Amount Due', 'Grand Total')",
    "utr_number": "UTR Number (e.g., 'UTR', 'Transaction ID', 'Reference Number')",
    "claim_number": "Claim Number or Settlement Number (e.g., 'Claim ID', 'Settlement ID', 'Case Number')",
    "payment_credited_date": "Payment Credited Date (e.g., 'Payment Date', 'Credit Date', 'Transaction Date')"
}

def extract_structured_data(file_path: str, model, selected_fields: list):
    try:
        # Generate prompt based on selected fields
        field_descriptions = [f"{field}: {AVAILABLE_FIELDS[field]}" for field in selected_fields]
        prompt = (
            f"Extract the following details from the provided PDF and return ONLY a valid JSON response:\n"
            f"{'; '.join(field_descriptions)}\n"
            "Handle variations in field names as indicated. For any field not found, use 'Not Found' as the value.\n"
            "IMPORTANT: Your response must contain ONLY the JSON object, without any additional text or markdown formatting."
        )
        
        # Process the file
        response = model.generate_content(
            [
                prompt,
                genai.upload_file(file_path)
            ]
        )
        
        # Clean the response text
        response_text = response.text.strip()
        
        # Sometimes Gemini adds markdown formatting, so we need to remove it
        if response_text.startswith("```json"):
            response_text = response_text[7:-3].strip()
        elif response_text.startswith("```"):
            response_text = response_text[3:-3].strip()
        
        # Parse JSON response
        extracted_data = json.loads(response_text)
        return extracted_data
        
    except json.JSONDecodeError:
        st.error(f"Failed to parse JSON response for {os.path.basename(file_path)}. Raw response: {response_text}")
        return None
    except Exception as e:
        st.error(f"Error processing {os.path.basename(file_path)}: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="PDF Data Extractor", layout="wide")
    st.title("Bulk PDF Data Extractor")
    st.subheader("Upload multiple PDF files and select fields to extract")

    # Initialize session state
    if 'failed_files' not in st.session_state:
        st.session_state.failed_files = []
    if 'processed_files' not in st.session_state:
        st.session_state.processed_files = []
    if 'processing_complete' not in st.session_state:
        st.session_state.processing_complete = False

    # Input for Gemini API key
    api_key = st.text_input("Enter your Gemini API Key", type="password")
    if not api_key:
        st.warning("Please enter a valid Gemini API Key to proceed.")
        return

    # Initialize Gemini client
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
    except Exception as e:
        st.error(f"Invalid API key or error initializing Gemini: {str(e)}")
        return

    # Multi-select for field selection
    st.write("Select the fields to extract from PDFs:")
    selected_fields = st.multiselect(
        "Fields",
        options=list(AVAILABLE_FIELDS.keys()),
        format_func=lambda x: AVAILABLE_FIELDS[x].split(" (")[0],
        default=["company_name", "invoice_number", "total_amount"]
    )
    
    if not selected_fields:
        st.warning("Please select at least one field to extract.")
        return

    # Multi-file uploader
    uploaded_files = st.file_uploader(
        "Upload multiple PDF files",
        type="pdf",
        accept_multiple_files=True
    )
    
    if uploaded_files:
        st.success(f"Selected {len(uploaded_files)} PDF files for processing")

    # Process button
    if st.button("Extract Data") and uploaded_files and api_key and selected_fields:
        st.session_state.processing_complete = False
        results = []
        st.session_state.failed_files = []
        
        # Create a progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # Create a temporary directory for uploaded files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Save uploaded files to temp directory
            saved_files = []
            for i, uploaded_file in enumerate(uploaded_files):
                file_path = os.path.join(temp_dir, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                saved_files.append(file_path)
            
            # Process each file
            for i, file_path in enumerate(saved_files):
                file_name = os.path.basename(file_path)
                
                # Update progress
                progress = int((i + 1) / len(saved_files) * 100)
                progress_bar.progress(progress)
                status_text.text(f"Processing {i+1} of {len(saved_files)}: {file_name}")
                
                # Process the file
                extracted_data = extract_structured_data(file_path, model, selected_fields)
                
                if extracted_data:
                    # Create a row with file name and only selected fields
                    row = {"File Name": file_name}
                    for field in selected_fields:
                        row[field] = extracted_data.get(field, "Not Found")
                    results.append(row)
                    st.session_state.processed_files.append(file_name)
                else:
                    st.session_state.failed_files.append(file_name)
            
            st.session_state.processing_complete = True
        
        # Display results after processing
        if results:
            # Convert results to DataFrame
            df = pd.DataFrame(results)
            
            # Display results
            st.write("Extracted Data:")
            st.dataframe(df)
            
            # Save to CSV
            csv_data = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="Download Data as CSV",
                data=csv_data,
                file_name="extracted_data.csv",
                mime="text/csv",
                key="download-csv"
            )
            
            # Show success message with stats
            success_rate = len(results)/len(uploaded_files)*100
            st.success(f"Data extraction completed! Success rate: {success_rate:.1f}%")
            
            # Show failed files if any
            if st.session_state.failed_files:
                st.warning(f"Failed to process {len(st.session_state.failed_files)} files:")
                st.write(st.session_state.failed_files)
        else:
            st.error("No data extracted from the provided PDFs.")

    # Reprocess failed files button
    if st.session_state.failed_files and st.session_state.processing_complete and st.button("Reprocess Failed Files"):
        with st.spinner(f"Reprocessing {len(st.session_state.failed_files)} failed files..."):
            results = []
            new_failures = []
            
            # Create a progress bar for reprocessing
            reprocess_bar = st.progress(0)
            reprocess_status = st.empty()
            
            for i, file_name in enumerate(st.session_state.failed_files):
                # Update progress
                progress = int((i + 1) / len(st.session_state.failed_files) * 100)
                reprocess_bar.progress(progress)
                reprocess_status.text(f"Reprocessing {i+1} of {len(st.session_state.failed_files)}: {file_name}")
                
                # Find the file in uploaded files
                for uploaded_file in uploaded_files:
                    if uploaded_file.name == file_name:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                            tmp_file.write(uploaded_file.getbuffer())
                            tmp_path = tmp_file.name
                        
                        extracted_data = extract_structured_data(tmp_path, model, selected_fields)
                        os.unlink(tmp_path)
                        
                        if extracted_data:
                            row = {"File Name": file_name}
                            for field in selected_fields:
                                row[field] = extracted_data.get(field, "Not Found")
                            results.append(row)
                            st.session_state.processed_files.append(file_name)
                        else:
                            new_failures.append(file_name)
                        break
            
            # Update failed files list
            st.session_state.failed_files = new_failures
            
            if results:
                # Convert results to DataFrame
                df = pd.DataFrame(results)
                
                # Display results
                st.write("Reprocessed Data:")
                st.dataframe(df)
                
                st.success(f"Successfully reprocessed {len(results)} files.")
                
                if st.session_state.failed_files:
                    st.warning(f"Still failed to process {len(st.session_state.failed_files)} files:")
                    st.write(st.session_state.failed_files)
            else:
                st.error("No additional files were successfully processed.")

if __name__ == "__main__":
    main()
