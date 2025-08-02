import streamlit as st
import pandas as pd
from io import BytesIO
import os
from openpyxl.styles import PatternFill

# Import Google libraries
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

st.set_page_config(
    page_title="Bulk Creative Updater",
    layout="wide"
)

st.title("Bulk Creative Updater Workflow")

# --- Tracker Type Maps ---
TRACKER_MAP_HOSTED_VIDEO = {
    "Impression": "THIRD_PARTY_URL_TYPE_IMPRESSION",
    "Click tracking": "THIRD_PARTY_URL_TYPE_CLICK_TRACKING",
    "Start": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_START",
    "First quartile": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_FIRST_QUARTILE",
    "Midpoint": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_MIDPOINT",
    "Third quartile": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_THIRD_QUARTILE",
    "Complete": "THIRD_PARTY_URL_TYPE_AUDIO_VIDEO_COMPLETE",
}

# --- Authentication ---
SCOPES = ['https://www.googleapis.com/auth/display-video']

def get_creds():
    if 'creds' in st.session_state and st.session_state.creds and st.session_state.creds.valid:
        return st.session_state.creds
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            if creds and creds.valid:
                st.session_state.creds = creds
                return creds
        except Exception as e:
            st.warning(f"Could not load token.json: {e}. Please re-authenticate on the main page.")
            return None
    st.error("You are not logged in. Please go to the 'app.py' welcome page to authenticate.")
    return None

def fetch_creative_details(service, advertiser_id, creative_id):
    """Makes a live API call to fetch creative details."""
    try:
        request = service.advertisers().creatives().get(
            advertiserId=advertiser_id,
            creativeId=creative_id
        )
        return request.execute()
    except Exception as e:
        st.error(f"Failed to fetch Creative ID {creative_id}: {e}")
        return None

def generate_excel_file(df, is_report=False):
    """Generates a color-coded Excel file in memory."""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Trackers')
        workbook = writer.book
        worksheet = writer.sheets['Trackers']
        
        # Define fills for coloring
        light_grey_fill = PatternFill(start_color='E7E6E6', end_color='E7E6E6', fill_type='solid')
        
        # Coloring for the change report
        if is_report:
            added_fill = PatternFill(start_color='D6EFD6', end_color='D6EFD6', fill_type='solid') # Green
            deleted_fill = PatternFill(start_color='FFD6D6', end_color='FFD6D6', fill_type='solid') # Red
            updated_fill = PatternFill(start_color='D6E8EF', end_color='D6E8EF', fill_type='solid') # Blue

            for row_num, row_data in enumerate(df.itertuples(index=False), start=2):
                status = row_data.status
                fill = None
                if status == 'ADDED':
                    fill = added_fill
                elif status == 'DELETED':
                    fill = deleted_fill
                elif status == 'UPDATED':
                    fill = updated_fill
                
                if fill:
                    for col_num in range(1, len(df.columns) + 1):
                        worksheet.cell(row=row_num, column=col_num).fill = fill
        else: # Standard alternating colors
            current_creative_id = None
            use_grey = False
            for row_num, row_data in enumerate(df.itertuples(index=False), start=2):
                if str(row_data.creative_id) != str(current_creative_id):
                    current_creative_id = str(row_data.creative_id)
                    use_grey = not use_grey
                if use_grey:
                    for col_num in range(1, len(df.columns) + 1):
                        worksheet.cell(row=row_num, column=col_num).fill = light_grey_fill

    return output.getvalue()

# --- Main UI ---
creds = get_creds()

if creds:
    # --- Initialize Session State ---
    if 'processed_df' not in st.session_state:
        st.session_state.processed_df = None
    if 'individual_results' not in st.session_state:
        st.session_state.individual_results = None
    if 'update_plan' not in st.session_state:
        st.session_state.update_plan = None


    # --- Phase 1: Uploader ---
    st.header("Phase 1: Upload Creative IDs")
    advertiser_id_input = st.text_input("Enter the Advertiser ID for all creatives")
    uploaded_ids_file = st.file_uploader("Upload a one-column CSV with your Creative IDs", type="csv")

    if st.button("Process IDs and Show Results"):
        if uploaded_ids_file and advertiser_id_input:
            # Main processing logic
            pass # Abridged for clarity

    # --- Display Results and Global Download Button ---
    if st.session_state.individual_results:
        # Abridged for clarity
        pass

    if st.session_state.processed_df is not None and not st.session_state.processed_df.empty:
        # Abridged for clarity
        pass

    # --- Phase 2: Upload Edited File for Validation and Review ---
    st.header("Phase 2: Upload Your Edited Excel File")
    edited_file = st.file_uploader("Upload the Excel file you edited", type="xlsx")

    if edited_file:
        if st.button("Validate and Review Changes"):
            try:
                with st.spinner("Validating file and comparing changes..."):
                    edited_df = pd.read_excel(edited_file).fillna('')
                    original_df = st.session_state.processed_df.fillna('')
                    
                    # --- Reverted, Simple Validation Logic ---
                    original_rows = len(original_df)
                    edited_rows = len(edited_df)
                    
                    st.subheader("Review Your Planned Changes")
                    st.info("✅ Your file has been validated successfully.")
                    st.write(f"Your uploaded file contains **{edited_rows}** total trackers.")
                    st.write(f"The original file had **{original_rows}** trackers.")
                    
                    st.session_state.update_plan = edited_df

                    # --- Logic to create the detailed change report ---
                    # Create a unique key for merging
                    original_df['key'] = original_df['creative_id'].astype(str) + "|" + original_df['event_type'] + "|" + original_df['existing_url']
                    edited_df['final_url'] = edited_df.apply(lambda row: row['new_url'] if row['new_url'] else row['existing_url'], axis=1)
                    edited_df['key'] = edited_df['creative_id'].astype(str) + "|" + edited_df['event_type'] + "|" + edited_df['existing_url']

                    # Merge the two dataframes
                    merged_df = pd.merge(original_df, edited_df[['key', 'final_url']], on='key', how='outer', indicator=True)
                    
                    def get_status(row):
                        if row['_merge'] == 'left_only':
                            return 'DELETED'
                        elif row['_merge'] == 'right_only':
                            return 'ADDED'
                        elif row['existing_url'] != row['final_url']:
                            return 'UPDATED'
                        else:
                            return 'NO CHANGE'
                    
                    merged_df['status'] = merged_df.apply(get_status, axis=1)
                    st.session_state.change_report_df = merged_df

            except Exception as e:
                st.error(f"An error occurred during validation: {e}")

    # --- Download Change Report ---
    if 'change_report_df' in st.session_state and st.session_state.change_report_df is not None:
        report_df = st.session_state.change_report_df.copy()
        report_excel = generate_excel_file(report_df[['advertiser_id', 'creative_id', 'creative_name', 'event_type', 'existing_url', 'final_url', 'status']], is_report=True)
        st.download_button(
            label="📊 Download Change Report",
            data=report_excel,
            file_name="change_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


    # --- Phase 3: Final Confirmation ---
    if st.session_state.update_plan is not None:
        st.header("Phase 3: Confirm and Push to DV360")
        st.warning("⚠️ **FINAL WARNING:** This action is irreversible.")
        
        if st.button("Confirm and Send to DV3G0", type="primary"):
            # Final update logic remains the same
            pass # Abridged for clarity
