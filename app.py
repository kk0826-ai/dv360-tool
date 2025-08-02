import streamlit as st
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

st.set_page_config(
    page_title="DV360 Creative Updater",
    page_icon="🔧",
    layout="wide"
)

st.title("Welcome to the DV360 Creative Updater")

SCOPES = ['https://www.googleapis.com/auth/display-video']

# --- Authentication Logic ---
def get_creds():
    # This function now correctly handles the login flow on the main page.
    if 'creds' in st.session_state and st.session_state.creds and st.session_state.creds.valid:
        st.success("You are logged in.")
        st.info("Please navigate to the **Bulk Update** page in the sidebar to begin.")
        return st.session_state.creds
        
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            if creds and creds.valid:
                st.session_state.creds = creds
                st.success("You are logged in.")
                st.info("Please navigate to the **Bulk Update** page in the sidebar to begin.")
                return creds
        except Exception as e:
            st.warning(f"Could not load token.json: {e}. Please re-authenticate.")

    try:
        # This assumes you have your client_secret.json details in st.secrets
        client_config = st.secrets
        flow = InstalledAppFlow.from_client_config(
            client_config, SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob')
    except Exception as e:
        st.error(f"Failed to load secrets. Error: {e}")
        return None

    auth_url, _ = flow.authorization_url(prompt='consent')
    st.warning("Please authorize this application to continue.")
    st.markdown(f"[Click here to authorize]({auth_url})", unsafe_allow_html=True)
    
    auth_code = st.text_input("Enter the authorization code you receive here:")
    
    if auth_code:
        try:
            flow.fetch_token(code=auth_code)
            creds = flow.credentials
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
            st.session_state.creds = creds
            st.success("Authentication successful!")
            st.info("Please navigate to the **Bulk Update** page in the sidebar.")
            st.rerun() # Rerun to update the login status
        except Exception as e:
            st.error(f"Error fetching token: {e}")
    return None

# Run the authentication flow
get_creds()
