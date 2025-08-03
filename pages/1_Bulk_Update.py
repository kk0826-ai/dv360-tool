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
        
        # New coloring for the final upload status report
        if is_report:
            failed_fill = PatternFill(start_color='FFD6D6', end_color='FFD6D6', fill_type='solid') # Red

            for row_num, row_data in enumerate(df.itertuples(index=False), start=2):
                status = getattr(row_data, 'upload_status', '')
                if status == '❌ Failed':
                    for col_num in range(1, len(df.columns) + 1):
                        worksheet.cell(row=row_num, column=col_num).fill = failed_fill
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
    # Abridged for clarity

    # --- Phase 1: Uploader ---
    st.header("Phase 1: Upload Creative IDs")
    advertiser_id_input = st.text_input("Enter the Advertiser ID for all creatives")
    uploaded_ids_file = st.file_uploader("Upload a one-column CSV with your Creative IDs", type="csv")

    if st.button("Process IDs and Show Results"):
        if uploaded_ids_file and advertiser_id_input:
            # Main processing logic... (abridged for clarity)
            pass

    # --- Display Results and Global Download Button ---
    if st.session_state.get('individual_results'):
        # Abridged for clarity
        pass

    if st.session_state.get('processed_df') is not None and not st.session_state.processed_df.empty:
        # Abridged for clarity
        pass


    # --- Phase 2: Upload Edited File for Validation and Review ---
    st.header("Phase 2: Upload Your Edited Excel File")
    st.info("To delete a tracker, type 'delete' in the `new_url` column. To add a tracker, add a new row and fill in the `new_url`.")
    edited_file = st.file_uploader("Upload the Excel file you edited", type="xlsx")

    if edited_file:
        if st.button("Validate and Review Changes"):
            try:
                with st.spinner("Validating file..."):
                    edited_df = pd.read_excel(edited_file).fillna('')
                    
                    deletes = edited_df[edited_df['new_url'].str.lower() == 'delete']
                    adds = edited_df[edited_df['existing_url'] == '']
                    updates = edited_df[(edited_df['new_url'] != '') & (edited_df['new_url'].str.lower() != 'delete') & (edited_df['existing_url'] != '')]
                    no_change = edited_df[(edited_df['new_url'] == '') & (edited_df['existing_url'] != '')]

                    st.subheader("Validation Complete")
                    st.write(f"🟢 **Trackers to be Added:** {len(adds)}")
                    st.write(f"🔴 **Trackers to be Deleted:** {len(deletes)}")
                    st.write(f"🔵 **Trackers to be Updated:** {len(updates)}")
                    st.write(f"⚪ **Trackers with No Change:** {len(no_change)}")
                    
                    st.session_state.update_plan = edited_df
            except Exception as e:
                st.error(f"An error occurred during validation: {e}")

    # --- Phase 3: Final Confirmation ---
    if 'update_plan' in st.session_state and st.session_state.update_plan is not None:
        st.header("Phase 3: Confirm and Push to DV360")
        st.warning("⚠️ **FINAL WARNING:** This action is irreversible.")
        
        if st.button("Confirm and Send to DV360", type="primary"):
            try:
                with st.spinner("Sending updates to the DV360 API..."):
                    plan_df = st.session_state.update_plan
                    service = build('displayvideo', 'v3', credentials=creds)
                    
                    upload_results = []

                    for creative_id, group in plan_df.groupby('creative_id'):
                        final_trackers = []
                        adv_id = group['advertiser_id'].iloc[0]
                        creative_name = group['creative_name'].iloc[0]

                        for _, row in group.iterrows():
                            if row['new_url'].lower() != 'delete':
                                url_to_use = row['new_url'] if str(row['new_url']).strip() else row['existing_url']
                                if str(row['event_type']).strip() and str(url_to_use).strip():
                                    api_type = TRACKER_MAP_HOSTED_VIDEO.get(row['event_type'], row['event_type'])
                                    final_trackers.append({"type": api_type, "url": str(url_to_use).strip()})
                        
                        try:
                            service.advertisers().creatives().patch(
                                advertiserId=str(adv_id),
                                creativeId=str(creative_id),
                                updateMask="thirdPartyUrls",
                                body={"thirdPartyUrls": final_trackers}
                            ).execute()
                            upload_results.append({
                                "creative_id": creative_id,
                                "creative_name": creative_name,
                                "upload_status": "✅ Success",
                                "details": ""
                            })
                        except Exception as e:
                            upload_results.append({
                                "creative_id": creative_id,
                                "creative_name": creative_name,
                                "upload_status": "❌ Failed",
                                "details": str(e)
                            })

                    st.session_state.final_upload_report = pd.DataFrame(upload_results)
                    st.success("All updates have been processed!")
                    
                    # Clear session state for the next run
                    for key in ['processed_df', 'individual_results', 'update_plan']:
                        if key in st.session_state:
                            del st.session_state[key]

            except Exception as e:
                st.error(f"An error occurred during the final update: {e}")
    
    # --- Final Report Download ---
    if 'final_upload_report' in st.session_state and st.session_state.final_upload_report is not None:
        st.header("Download Upload Status Report")
        report_excel = generate_excel_file(st.session_state.final_upload_report, is_report=True)
        st.download_button(
            label="📊 Download Upload Status Report",
            data=report_excel,
            file_name="upload_status_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
