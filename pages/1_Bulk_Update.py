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
        
        light_grey_fill = PatternFill(start_color='E7E6E6', end_color='E7E6E6', fill_type='solid')
        
        if is_report:
            added_fill = PatternFill(start_color='D6EFD6', end_color='D6EFD6', fill_type='solid')
            deleted_fill = PatternFill(start_color='FFD6D6', end_color='FFD6D6', fill_type='solid')
            updated_fill = PatternFill(start_color='D6E8EF', end_color='D6E8EF', fill_type='solid')

            for row_num, row_data in enumerate(df.itertuples(index=False), start=2):
                status = getattr(row_data, 'status', '')
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
        else:
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
    if 'change_report_updates' not in st.session_state:
        st.session_state.change_report_updates = None
    if 'change_report_adds_deletes' not in st.session_state:
        st.session_state.change_report_adds_deletes = None


    # --- Phase 1: Uploader ---
    st.header("Phase 1: Upload Creative IDs")
    advertiser_id_input = st.text_input("Enter the Advertiser ID for all creatives")
    uploaded_ids_file = st.file_uploader("Upload a one-column CSV with your Creative IDs", type="csv")

    if st.button("Process IDs and Show Results"):
        if uploaded_ids_file and advertiser_id_input:
            # Main processing logic... (abridged for clarity)
            pass

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

                    # --- New, More Robust Validation Logic ---
                    # Create a unique key for each tracker
                    original_df['key'] = original_df['creative_id'].astype(str) + "|" + original_df['event_type'] + "|" + original_df['existing_url']
                    edited_df['key'] = edited_df['creative_id'].astype(str) + "|" + edited_df['event_type'] + "|" + edited_df['existing_url']
                    
                    # Merge the dataframes to find all changes
                    merged_df = pd.merge(original_df, edited_df[['key', 'new_url']], on='key', how='outer', indicator=True)
                    
                    updates_list = []
                    adds_deletes_list = []

                    # Process the merged dataframe to classify each change
                    for _, row in merged_df.iterrows():
                        status = ""
                        # Deleted rows only exist in the original (left_only)
                        if row['_merge'] == 'left_only':
                            status = 'DELETED'
                            adds_deletes_list.append(row)
                        # Added rows only exist in the edited (right_only)
                        elif row['_merge'] == 'right_only':
                            status = 'ADDED'
                            adds_deletes_list.append(row)
                        # Updated rows have a new_url that is different from the original
                        elif row['new_url_y'] and row['new_url_y'] != row['existing_url']:
                            status = 'UPDATED'
                            updates_list.append(row)
                    
                    st.subheader("Validation Complete")
                    if not adds_deletes_list and not updates_list:
                        st.success("✅ No changes were detected in the uploaded file.")
                        st.session_state.update_plan = None # Prevent Phase 3 from showing
                    else:
                        st.info("Please review the changes below by downloading the reports.")
                        st.session_state.update_plan = edited_df # Allow Phase 3 to proceed

                    # Store reports in session state for download
                    st.session_state.change_report_updates = pd.DataFrame(updates_list) if updates_list else None
                    st.session_state.change_report_adds_deletes = pd.DataFrame(adds_deletes_list) if adds_deletes_list else None
            except Exception as e:
                st.error(f"An error occurred during validation: {e}")

    # --- Download Change Reports ---
    if st.session_state.get('change_report_updates') is not None and not st.session_state.change_report_updates.empty:
        report_df = st.session_state.change_report_updates
        report_excel = generate_excel_file(report_df.rename(columns={'new_url_y': 'new_url'}), is_report=True)
        st.download_button(
            label="📊 Download Update Report",
            data=report_excel,
            file_name="update_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="updates_download"
        )
    
    if st.session_state.get('change_report_adds_deletes') is not None and not st.session_state.change_report_adds_deletes.empty:
        report_df = st.session_state.change_report_adds_deletes
        report_excel = generate_excel_file(report_df, is_report=True)
        st.download_button(
            label="🚨 Download Add/Delete Report",
            data=report_excel,
            file_name="add_delete_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="adds_deletes_download"
        )


    # --- Phase 3: Final Confirmation ---
    if st.session_state.get('update_plan') is not None:
        st.header("Phase 3: Confirm and Push to DV360")
        st.warning("⚠️ **FINAL WARNING:** This action is irreversible.")
        
        if st.button("Confirm and Send to DV360", type="primary"):
            # Final update logic remains the same
            pass # Abridged for clarity
