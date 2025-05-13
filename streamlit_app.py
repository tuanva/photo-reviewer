import os
import cv2
import numpy as np
from PIL import Image
import streamlit as st
# import face_recognition
from io import BytesIO
import requests
import json
import re
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

def download_file_from_google_drive(file_id):
    """
    Downloads a publicly shared file from Google Drive without authentication
    """
    URL = f"https://drive.google.com/uc?id={file_id}&export=download"
    
    try:
        response = requests.get(URL)
        return BytesIO(response.content)
    except Exception as e:
        st.error(f"Error downloading file: {str(e)}")
        return None

def list_files_in_folder(folder_id):
    """
    Lists files in a publicly shared Google Drive folder using the Google Drive API
    """
    try:
        st.write("🔍 Fetching folder contents using Google Drive API...")
        
        if "google_api_key" not in st.secrets:
            st.error("Google Drive API key not found in Streamlit secrets.")
            st.info("Please add your Google Drive API key to .streamlit/secrets.toml file with the key 'google_api_key'")
            st.stop()
            
        # Create a service object using API v3
        service = build('drive', 'v3', developerKey=st.secrets.google_api_key)
        
        # Set up the query to find images in the folder
        query = f"'{folder_id}' in parents and (mimeType contains 'image/jpeg' or mimeType contains 'image/png')"
        
        # List files in the folder
        results = service.files().list(
            q=query,
            pageSize=1000,
            fields="files(id, name, mimeType)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        files = results.get('files', [])
        
        if not files:
            st.write("No images found in the folder")
            return []
            
        # Filter and format the results
        image_files = []
        for file in files:
            if file['name'].lower().endswith(('.jpg', '.jpeg', '.png')):
                image_files.append({
                    'id': file['id'],
                    'name': file['name']
                })
                # st.write(f"Found image: {file['name']}")
        
        st.write(f"Total images found: {len(image_files)}")
        return image_files
            
    except HttpError as error:
        st.error(f"Google Drive API error: {error}")
        return []
    except Exception as e:
        st.error(f"Error listing files in folder: {str(e)}")
        st.write(f"Error details: {str(e)}")
        return []


def extract_file_id_from_url(url):
    """
    Extracts file ID from various formats of Google Drive URLs
    """
    # Don't process empty strings or None
    if not url:
        return None
        
    # Pattern for IDs extracted from URLs (at least 5 chars)
    url_id_pattern = r'^[a-zA-Z0-9_-]{5,}$'
    
    if 'file/d/' in url:
        # Handle URLs like: https://drive.google.com/file/d/{FILE_ID}/view
        start = url.find('file/d/') + 7
        end = url.find('/', start)
        file_id = url[start:end] if end != -1 else url[start:]
        return {'type': 'file', 'id': file_id} if file_id and re.match(url_id_pattern, file_id) else None
    elif 'folders/' in url:
        # Handle URLs like: https://drive.google.com/drive/folders/{FOLDER_ID}
        start = url.find('folders/') + 8
        end = url.find('?', start)
        folder_id = url[start:end] if end != -1 else url[start:]
        return {'type': 'folder', 'id': folder_id} if folder_id and re.match(url_id_pattern, folder_id) else None
    elif 'id=' in url:
        # Handle URLs like: https://drive.google.com/uc?id={FILE_ID}
        file_id = url.split('id=')[1].split('&')[0]
        return {'type': 'file', 'id': file_id} if file_id and re.match(url_id_pattern, file_id) else None
    return None

def evaluate_image(filepath):
    img = cv2.imread(filepath)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    score = {}

    # Calculate base metrics
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    brightness = np.mean(gray)
    contrast = np.std(gray)
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    saturation = np.mean(hsv[:, :, 1])
    overexposed = np.mean(img > 240) > 0.05
    underexposed = np.mean(img < 15) > 0.05

    # Store raw metrics
    score['sharpness'] = round(sharpness, 2)
    score['brightness'] = round(brightness, 2)
    score['contrast'] = round(contrast, 2)
    score['saturation'] = round(saturation, 2)
    score['overexposed'] = overexposed
    score['underexposed'] = underexposed

    # Calculate normalized scores and final score
    norm_sharpness = min(sharpness / 300, 1.0)
    norm_contrast = min(contrast / 100, 1.0)
    norm_saturation = min(saturation / 150, 1.0)
    exposure_penalty = 1.0 if (overexposed or underexposed) else 0.0

    final_score = (
        0.4 * norm_sharpness +
        0.2 * norm_contrast +
        0.2 * norm_saturation +
        0.2 * (1 - exposure_penalty)
    )
    
    score['final_score'] = round(final_score, 3)

    # try:
    #     face_image = face_recognition.load_image_file(filepath)
    #     face_locations = face_recognition.face_locations(face_image)
    #     score['faces'] = len(face_locations)
    # except:

    #temporary remove face detection
    score['faces'] = 0

    return score

def analyze_folder(folder):
    results = []
    for fname in os.listdir(folder):
        if fname.lower().endswith(('jpg', 'jpeg', 'png')):
            path = os.path.join(folder, fname)
            score = evaluate_image(path)
            score['filename'] = fname
            score['path'] = path
            results.append(score)
    return results

def get_downloaded_files(folder_path):
    """
    Get a list of already downloaded files in a folder
    Returns a dict with filenames as keys for quick lookup
    """
    if not os.path.exists(folder_path):
        return {}
    
    downloaded = {}
    for fname in os.listdir(folder_path):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            downloaded[fname] = True
    return downloaded

def main():
    st.title("📸 Photo Quality Reviewer")

    # Create a session state for tracking the selected image
    if 'selected_image' not in st.session_state:
        st.session_state.selected_image = None

    with st.sidebar:
        st.header("Google Drive Setup")
        st.markdown("""
        ### Instructions:
        1. Share your Google Drive images/folder publicly
        2. Paste the sharing link or file ID below
        """)
        drive_input = st.text_input("Enter Google Drive sharing link or file ID:")
        
        if drive_input:
            result = extract_file_id_from_url(drive_input)
            if result:
                # Create a specific folder for this Google Drive folder/file
                folder_path = os.path.join('photos', result['id'])
                downloaded_files = get_downloaded_files(folder_path)
                
                if result['type'] == 'file':
                    file_name = f"image_{result['id']}.jpg"
                    file_path = os.path.join(folder_path, file_name)
                    
                    if file_name not in downloaded_files:
                        st.write("🔄 Downloading image...")
                        os.makedirs(folder_path, exist_ok=True)
                        file_data = download_file_from_google_drive(result['id'])
                        
                        if file_data:
                            try:
                                image = Image.open(file_data)
                                image.save(file_path)
                                st.success("✅ Image downloaded successfully!")
                            except Exception as e:
                                st.error(f"Error processing image: {str(e)}")
                    else:
                        st.success("✅ Image already downloaded!")
                
                else:  # folder
                    st.write("🔄 Checking folder contents...")
                    files = list_files_in_folder(result['id'])
                    
                    if files:
                        # Filter out already downloaded files
                        files_to_download = [f for f in files if f['name'] not in downloaded_files]
                        
                        if files_to_download:
                            st.write(f"Downloading {len(files_to_download)} new images...")
                            os.makedirs(folder_path, exist_ok=True)
                            
                            progress_bar = st.progress(0)
                            for i, file in enumerate(files_to_download):
                                # st.write(f"Downloading {file['name']}...")
                                file_data = download_file_from_google_drive(file['id'])
                                
                                if file_data:
                                    try:
                                        image = Image.open(file_data)
                                        file_path = os.path.join(folder_path, file['name'])
                                        image.save(file_path)
                                    except Exception as e:
                                        st.error(f"Error processing {file['name']}: {str(e)}")
                                
                                progress_bar.progress((i + 1) / len(files_to_download))
                            
                            st.success(f"✅ Downloaded {len(files_to_download)} new images successfully!")
                        else:
                            st.success(f"✅ All {len(files)} images already downloaded!")
                    else:
                        st.error("No images found in the folder or unable to access folder contents")
            else:
                st.error("Invalid Google Drive URL format")

    # Update the photos path to use the current folder ID if it exists
    current_folder = None
    if 'result' in locals() and result and os.path.exists(os.path.join('photos', result['id'])):
        current_folder = os.path.join('photos', result['id'])
    
    if current_folder and os.path.exists(current_folder):
        photos = analyze_folder(current_folder)

        st.sidebar.header("Filter")
        min_faces = st.sidebar.slider("Minimum Faces", min_value=0, max_value=5, value=0)
        max_brightness = st.sidebar.slider("Max Brightness", min_value=0, max_value=255, value=255)
        min_sharpness = st.sidebar.slider("Min Sharpness", min_value=0, max_value=1000, value=0)

        # Apply filters only if they're not at their minimum values
        filtered = photos
        if min_faces > 0:
            filtered = [p for p in filtered if p['faces'] >= min_faces]
        if max_brightness < 255:
            filtered = [p for p in filtered if p['brightness'] <= max_brightness]
        if min_sharpness > 0:
            filtered = [p for p in filtered if p['sharpness'] >= min_sharpness]

        st.markdown(f"### ✅ Showing {len(filtered)} photos out of {len(photos)} total")
        
        if not filtered:
            st.warning("No photos match the current filter criteria. Try adjusting the filters.")
        
        # Show preview if an image is selected
        if st.session_state.selected_image:
            st.markdown("### 🖼️ Preview")
            preview_col1, preview_col2 = st.columns([3, 1])
            with preview_col1:
                st.image(st.session_state.selected_image['path'])
            with preview_col2:
                st.markdown(f"**{st.session_state.selected_image['filename']}**")
                st.markdown(
                    f"""
                    - Score: `{st.session_state.selected_image['final_score']}`
                    - Faces: `{st.session_state.selected_image['faces']}`
                    - Sharpness: `{st.session_state.selected_image['sharpness']}`
                    """
                )
                if st.button("Close Preview", key="close_preview"):
                    st.session_state.selected_image = None
                    st.rerun()
            st.markdown("---")
        
        # Display thumbnails in a 3-column grid
        # Process images in groups of 3
        for i in range(0, len(filtered), 3):
            cols = st.columns(3)
            # Handle each column in the current row
            for j in range(3):
                idx = i + j
                if idx < len(filtered):
                    photo = filtered[idx]
                    with cols[j]:
                        # Show the image and make it clickable
                        if st.button("📸", key=f"thumb_{photo['path']}", help="Click to preview"):
                            st.session_state.selected_image = photo
                            st.rerun()
                        st.image(photo['path'], use_container_width=True)
                        st.markdown(f"**{photo['filename']}**")
                        st.markdown(f"Score: `{photo['final_score']}`")
    else:
        st.info("📁 Waiting for photo download...")

if __name__ == "__main__":
    main()
