import unittest
from unittest.mock import patch, MagicMock
from streamlit_app import extract_file_id_from_url, list_files_in_folder, download_file_from_google_drive
from io import BytesIO

class TestGoogleDriveFunctions(unittest.TestCase):
    def test_extract_file_id_from_url(self):
        # Test direct file ID
        self.assertEqual(
            extract_file_id_from_url('abc123def456'),
            {'type': 'file', 'id': 'abc123def456'}
        )

        # Test file URL
        self.assertEqual(
            extract_file_id_from_url('https://drive.google.com/file/d/123456/view'),
            {'type': 'file', 'id': '123456'}
        )

        # Test folder URL
        self.assertEqual(
            extract_file_id_from_url('https://drive.google.com/drive/folders/123456'),
            {'type': 'folder', 'id': '123456'}
        )

        # Test folder URL with query parameters
        self.assertEqual(
            extract_file_id_from_url('https://drive.google.com/drive/folders/123456?usp=sharing'),
            {'type': 'folder', 'id': '123456'}
        )

        # Test invalid URLs
        self.assertIsNone(extract_file_id_from_url('invalid-url'))
        self.assertIsNone(extract_file_id_from_url('http://example.com'))
        self.assertIsNone(extract_file_id_from_url(''))

    @patch('requests.get')
    def test_list_files_in_folder_success(self, mock_get):
        # Mock successful response with typical Google Drive folder structure
        mock_response = MagicMock()
        mock_response.text = '''
        AF_initDataCallback({
            data: [
                [],
                [
                    [
                        ["123456", "test.jpg", "image/jpeg"],
                        ["789012", "document.pdf", "application/pdf"],
                        ["345678", "photo.png", "image/png"]
                    ]
                ]
            ],
            sideChannel: {}
        });
        '''
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        files = list_files_in_folder('folder-id')
        self.assertEqual(len(files), 2)  # Should only include jpg and png files
        self.assertEqual(files[0], {'id': '123456', 'name': 'test.jpg'})
        self.assertEqual(files[1], {'id': '345678', 'name': 'photo.png'})

    @patch('requests.get')
    def test_list_files_in_folder_empty(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = 'AF_initDataCallback({data:[], sideChannel: {}});'
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        files = list_files_in_folder('folder-id')
        self.assertEqual(files, [])

    @patch('requests.get')
    def test_list_files_in_folder_error(self, mock_get):
        mock_get.side_effect = Exception('Network error')
        files = list_files_in_folder('folder-id')
        self.assertEqual(files, [])

    @patch('requests.get')
    def test_download_file_from_google_drive_success(self, mock_get):
        mock_response = MagicMock()
        mock_response.content = b'fake-image-data'
        mock_get.return_value = mock_response

        result = download_file_from_google_drive('file-id')
        self.assertIsInstance(result, BytesIO)
        self.assertEqual(result.getvalue(), b'fake-image-data')

    @patch('requests.get')
    def test_download_file_from_google_drive_error(self, mock_get):
        mock_get.side_effect = Exception('Network error')
        result = download_file_from_google_drive('file-id')
        self.assertIsNone(result)

if __name__ == '__main__':
    unittest.main()