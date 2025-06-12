import streamlit as st
import os
import pandas as pd
from google import generativeai as genai
import json
import glob

# Available fields for extraction
AVAILABLE_FIELDS = {
    "company_name": "Name of the Company (e.g., 'Company', 'Vendor', 'Organization')",
    "invoice_number": "Invoice Number (e.g., 'Invoice No.', 'Bill Number', 'Invoice ID')",
    "total_amount": "Total Amount (e.g., 'Total', 'Amount Due', 'Grand Total')",
    "utr_number": "UTR Number (e.g., 'UTR', 'Transaction ID', 'Reference Number')",
    "claim_number": "Claim Number or Settlement Number (e.g., 'Claim ID', 'Settlement ID', 'Case Number')",
    "payment_credited_date": "Payment Credited Date (e.g., 'Payment Date', 'Credit Date', 'Transaction Date')"
}

# ... (keep all your imports and AVAILABLE_FIELDS the same)

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

# Streamlit app
def main():
    st.set_page_config(page_title="PDF Data Extractor", layout="wide")
    st.title("Bulk PDF Data Extractor")
    st.subheader("Upload a folder of PDF files and select fields to extract")

    # Initialize session state for tracking failed files
    if 'failed_files' not in st.session_state:
        st.session_state.failed_files = []
    if 'processed_files' not in st.session_state:
        st.session_state.processed_files = []

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

    # Folder path input
    st.write("Enter the path to the folder containing PDF files (e.g., C:/Users/YourName/Documents/pdfs):")
    folder_path = st.text_input("Folder Path")
    uploaded_files = []
    if folder_path and os.path.isdir(folder_path):
        uploaded_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        if not uploaded_files:
            st.warning("No PDF files found in the specified folder.")
        else:
            st.write(f"Found {len(uploaded_files)} PDF files in the folder.")

    # Process button
    if st.button("Extract Data") and uploaded_files and api_key and selected_fields:
        with st.spinner("Processing PDFs..."):
            # Initialize DataFrame to store results
            results = []
            st.session_state.failed_files = []  # Reset failed files list
            
            for file_path in uploaded_files:
                file_name = os.path.basename(file_path)
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
    if st.session_state.failed_files and st.button("Reprocess Failed Files"):
        with st.spinner(f"Reprocessing {len(st.session_state.failed_files)} failed files..."):
            results = []
            new_failures = []
            
            for file_name in st.session_state.failed_files:
                file_path = os.path.join(folder_path, file_name)
                extracted_data = extract_structured_data(file_path, model, selected_fields)
                
                if extracted_data:
                    # Create a row with file name and only selected fields
                    row = {"File Name": file_name}
                    for field in selected_fields:
                        row[field] = extracted_data.get(field, "Not Found")
                    results.append(row)
                    st.session_state.processed_files.append(file_name)
                else:
                    new_failures.append(file_name)
            
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
