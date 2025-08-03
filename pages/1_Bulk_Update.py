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
            failed_fill = PatternFill(start_color='FFD6D6', end_color='FFD6D6', fill_type='solid') # Red

            for row_num, row_data in enumerate(df.itertuples(index=False), start=2):
                status = getattr(row_data, 'upload_status', '')
                if status == '❌ Failed':
                    for col_num in range(1, len(df.columns) + 1):
                        worksheet.cell(row=row_num, column=col_num).fill = failed_fill
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
    if 'final_upload_report' not in st.session_state:
        st.session_state.final_upload_report = None


    # --- Phase 1: Uploader ---
    st.header("Phase 1: Upload Creative IDs")
    advertiser_id_input = st.text_input("Enter the Advertiser ID for all creatives")
    uploaded_ids_file = st.file_uploader("Upload a one-column CSV with your Creative IDs", type="csv")

    if st.button("Process IDs and Show Results"):
        if uploaded_ids_file and advertiser_id_input:
            try:
                raw_text = uploaded_ids_file.getvalue().decode('utf-8')
                lines = raw_text.splitlines()
                creative_ids = [line.strip() for line in lines if line.strip() and line.strip().lower() != 'creative_id']

                if not creative_ids:
                    st.error("The uploaded file contains no valid Creative IDs.")
                else:
                    service = build('displayvideo', 'v3', credentials=creds)
                    all_trackers_data = []
                    individual_results_list = []
                    
                    with st.spinner(f"Fetching data for {len(creative_ids)} creatives..."):
                        progress_bar = st.progress(0)
                        for i, creative_id in enumerate(creative_ids):
                            details = fetch_creative_details(service, advertiser_id_input, creative_id)
                            individual_results_list.append(details)
                            
                            if details:
                                trackers = details.get("thirdPartyUrls", [])
                                creative_name = details.get("displayName", "N/A")
                                reverse_map = {v: k for k, v in TRACKER_MAP_HOSTED_VIDEO.items()}

                                if trackers:
                                    for tracker in trackers:
                                        api_type = tracker.get('type')
                                        event_type = reverse_map.get(api_type, api_type)
                                        all_trackers_data.append({
                                            "advertiser_id": advertiser_id_input,
                                            "creative_id": creative_id,
                                            "creative_name": creative_name,
                                            "event_type": event_type,
                                            "existing_url": tracker.get("url"),
                                            "new_url": ""
                                        })
                                else:
                                    all_trackers_data.append({
                                        "advertiser_id": advertiser_id_input,
                                        "creative_id": creative_id,
                                        "creative_name": creative_name,
                                        "event_type": "",
                                        "existing_url": "",
                                        "new_url": ""
                                    })
                            progress_bar.progress((i + 1) / len(creative_ids))
                    
                    st.session_state.individual_results = individual_results_list
                    st.session_state.processed_df = pd.DataFrame(all_trackers_data)
                    st.success("Data extraction complete.")
            except Exception as e:
                st.error(f"An error occurred: {e}")
        else:
            st.warning("Please provide an Advertiser ID and upload a file.")

    # --- Display Results and Global Download Button ---
    if st.session_state.get('individual_results'):
        st.header("Extracted Creative Details")
        st.info("Click on each creative to view its trackers.")
        for creative_data in st.session_state.individual_results:
            if creative_data:
                name = creative_data.get('displayName', 'N/A')
                c_id = creative_data.get('creativeId', 'N/A')
                with st.expander(f"Creative: {name} (ID: {c_id})"):
                    trackers = creative_data.get("thirdPartyUrls", [])
                    if trackers:
                        reverse_map = {v: k for k, v in TRACKER_MAP_HOSTED_VIDEO.items()}
                        display_data = [{"event_type": reverse_map.get(t.get('type'), t.get('type')), "url": t.get('url')} for t in trackers]
                        st.dataframe(pd.DataFrame(display_data))
                    else:
                        st.write("No third-party trackers found.")

    if st.session_state.get('processed_df') is not None and not st.session_state.processed_df.empty:
        st.header("Download Combined File")
        excel_data = generate_excel_file(st.session_state.processed_df)
        st.download_button(
            label="📥 Download Combined Excel File to Edit",
            data=excel_data,
            file_name="dv360_trackers_to_edit.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


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
    if st.session_state.get('update_plan') is not None:
        st.header("Phase 3: Confirm and Push to DV360")
        st.warning("⚠️ **FINAL WARNING:** This action is irreversible.")
        
        if st.button("Confirm and Send to DV360", type="primary"):
            try:
                with st.spinner("Sending updates to the DV360 API..."):
                    plan_df = st.session_state.update_plan
                    service = build('displayvideo', 'v3', credentials=creds)
                    
                    upload_results_list = []

                    for creative_id, group in plan_df.groupby('creative_id'):
                        final_trackers = []
                        adv_id = group['advertiser_id'].iloc[0]
                        
                        for _, row in group.iterrows():
                            if row['new_url'].lower() != 'delete':
                                url_to_use = row['new_url'] if str(row['new_url']).strip() else row['existing_url']
                                if str(row['event_type']).strip() and str(url_to_use).strip():
                                    api_type = TRACKER_MAP_HOSTED_VIDEO.get(row['event_type'], row['event_type'])
                                    final_trackers.append({"type": api_type, "url": str(url_to_use).strip()})
                        
                        status = "✅ Success"
                        details_msg = ""
                        try:
                            service.advertisers().creatives().patch(
                                advertiserId=str(adv_id),
                                creativeId=str(creative_id),
                                updateMask="thirdPartyUrls",
                                body={"thirdPartyUrls": final_trackers}
                            ).execute()
                        except Exception as e:
                            status = "❌ Failed"
                            details_msg = str(e)
                        
                        # Add a status to each row of the original group
                        group['upload_status'] = status
                        group['details'] = details_msg
                        upload_results_list.append(group)

                    st.session_state.final_upload_report = pd.concat(upload_results_list)
                    st.success("All updates have been processed!")
                    
                    # Clear session state for the next run
                    for key in ['processed_df', 'individual_results', 'update_plan']:
                        if key in st.session_state:
                            del st.session_state[key]

            except Exception as e:
                st.error(f"An error occurred during the final update: {e}")
    
    # --- Final Report Download ---
    if st.session_state.get('final_upload_report') is not None:
        st.header("Download Upload Status Report")
        report_excel = generate_excel_file(st.session_state.final_upload_report, is_report=True)
        st.download_button(
            label="📊 Download Upload Status Report",
            data=report_excel,
            file_name="upload_status_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
