"""
This module provides functionalities to upload files.
Convert JSON to CSV and allow dowloading the CSV.
"""
import os
import logging
from werkzeug.utils import secure_filename
from flask import Flask, request, jsonify, send_from_directory, redirect, url_for
from flask_cors import CORS
from config import CORS_ORIGINS
from Scantron import Scantron95945

app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/*": {"origins": CORS_ORIGINS}})

class AppServer:
    """
    Class for managing routes and functionalities of the Flask app.
    """
    def __init__(self, flask_app):
        """
        Initializes the AppServer class.

        Parameters:
            flask_app (Flask): The Flask application instance.
        """
        self.app = flask_app
        self.uploads_dir = os.path.join(self.app.instance_path, 'uploads')
        os.makedirs(self.uploads_dir, exist_ok=True)
        logging.basicConfig(level=logging.DEBUG)
        self.file_info = {}
        self.csv_files = {}
        self.routes()

    def routes(self):
        """
        Defines the routes for various functionalities of the app.
        """
        self.app.route('/', methods=['GET'])(self.frontend)
        self.app.route('/static/<path:path>',methods=['GET'])(self.serve_static)
        self.app.route('/assets/<path:path>',methods=['GET'])(self.serve_assets)
        self.app.route('/api/data', methods=['GET'])(self.get_data)
        self.app.route('/api/message', methods=['POST'])(self.receive_message)
        self.app.route('/api/upload', methods=['POST'])(self.file_upload)
        self.app.route('/api/process_pdf', methods=['POST'])(self.process_pdf)
        self.app.route('/api/download_csv/<file_id>', methods=['GET'])(self.download_csv)
        self.app.route('/api/csv_acknowledgment/<file_id>', methods=['POST'])(self.csv_acknowledgment)

    def frontend(self):
        """
        Serves the frontend of the web application.

        This method handles the request to the root URL and serves the main HTML file 
        (typically 'index.html') from the 'static' directory, which is the entry point 
        for the frontend of the application.

        Returns:
            Response: The HTML content of the 'index.html' file located in the 'static' directory.
        """
        return send_from_directory('static', 'index.html')

    def serve_static(self,path):
        """
        Serves static files from the 'static' directory.

        This method handles requests for static files by serving them from the 'static' 
        directory based on the given path. It can serve various types of static content 
        such as JavaScript, CSS, images, etc.

        Args:
            path (str): The relative path to the static file within the 'static' directory.

        Returns:
            Response: The content of the requested static file.
        """
        return send_from_directory('static', path)

    def serve_assets(self,path):
        """
        Redirects to serve asset files from the 'assets' subdirectory within 'static'.

        This method handles requests for assets by redirecting them to the appropriate 
        static file path within the 'assets' subdirectory. It constructs the new path and 
        then uses the 'serve_static' method to serve the file.

        Args:
            path (str): The relative path to the asset file within the 'assets' subdirectory.

        Returns:
            Response: A redirect response to the constructed URL for the asset file.
        """
        return redirect(url_for('serve_static', path=f'assets/{path}'))

    def get_data(self):
        """
        Returns a simple message as JSON data.

        Returns:
            dict: JSON data with a message.
        """
        data = {"message": "Hello from Flask!"}
        return jsonify(data)

    def receive_message(self):
        """
        Receives a message from the client and logs it.

        Returns:
            dict: JSON data indicating successful message reception.
        """
        message_data = request.json
        message = message_data.get('message', '')
        print(f"Received message: {message}")
        return jsonify({"status": "success", "message": "Message received successfully!"})

    def file_upload(self):
        """
        Handles file upload requests, processes PDF files, and returns CSV data.
        Allows the user to specify whether the sheet is a standard Scantron or a custom sheet.
        """
        if 'file' not in request.files or 'sheetType' not in request.form:
            return jsonify({"status": "error", "message": "No file or sheet type in the request"})

        file = request.files['file']
        sheet_type = request.form['sheetType']  # Get the sheet type from the form

        if file.filename == '':
            return jsonify({"status": "error", "message": "No selected file"})

        if file and file.filename.lower().endswith('.pdf'):
            if sheet_type == "custom":
                # If it's a custom sheet, return "Not yet supported"
                return jsonify({
                    "status": "custom_sheet",
                    "message": "Custom sheets are not yet supported"
                })

            try:
                filename = secure_filename(file.filename)
                file_path = os.path.join(self.uploads_dir, filename)
                file.save(file_path)

                file_id = os.urandom(16).hex()
                self.file_info[file_id] = {
                    'filename': filename,
                    'path': file_path,
                    'processed': False
                }

                response_data = self.process_pdf(file_path, file_id)
                os.remove(file_path)

                return jsonify({"status": "success", "message": "PDF processed successfully", "file_id": file_id, "data": response_data})

            except Exception as e:
                return jsonify({"status": "error", "message": f"Error processing PDF: {e}"})

        else:
            return jsonify({"status": "error", "message": "Only PDF files are allowed"})

    def process_pdf(self, pdf_file, file_id):
        """
        Processes a PDF file to extract responses and convert them to CSV.

        Parameters:
            pdf_file (str): Path to the PDF file.
            file_id (str): Unique identifier for the file.

        Returns:
            str: Name of the generated CSV file.
        """
        try:
            scantron = Scantron95945(pdf_file)
            data = scantron.extract_responses()
            #print("Received the JSON data as: ", data)

            csv_data = self.transform_json_to_csv(data)
            csv_filename = f'output_{file_id}.csv'
            csv_file_path = os.path.join(self.uploads_dir, csv_filename)

            with open(csv_file_path, 'w', newline='', encoding='utf-8') as csv_file:
                csv_file.write(csv_data)

            self.csv_files[file_id] = {'filename': csv_filename, 'path': csv_file_path}

            self.file_info[file_id]['processed'] = True

            return csv_filename

        except Exception as e:
            logging.error("Error processing PDF: %s", e)
            return ''

    def transform_json_to_csv(self, json_data):
        """
        Transforms JSON data to CSV format.

        Parameters:
            json_data (dict): JSON data to be converted to CSV.

        Returns:
            str: CSV data as a string.
        """
        csv_data = ''
        print("The JSON data received is:", json_data)

        if not isinstance(json_data, dict) or 'students' not in json_data:
            print("Invalid JSON data format")
            return csv_data

        students = json_data['students']
        if not students:
            print("No student data found")
            return csv_data

        student_data = students[0]
        if 'answers' not in student_data:
            print("No 'answers' key found in student data")
            return csv_data

        keys = student_data['answers'].keys()
        print("Keys:", keys)
        csv_data += ','.join(['studentID'] + list(keys)) + '\n'

        for student in students:
            student_id = student.get('studentID', '')
            answers = []
            for key in keys:
                answer = student['answers'].get(key, '')
                if isinstance(answer, list):
                    answer = '|'.join(answer)
                elif answer is None:
                    answer = ''
                answers.append(answer)
            print("Student ID:", student_id)
            print("Answers:", answers)
            csv_data += ','.join([student_id] + answers) + '\n'

        print("The CSV data converted is: ", csv_data)
        return csv_data

    def download_csv(self, file_id):
        """
        Allows downloading of a CSV file.

        Parameters:
            file_id (str): Unique identifier for the file.

        Returns:
            Response: Flask response object containing the CSV file.
        """
        try:
            if file_id not in self.csv_files:
                return jsonify({"status": "error", "message": "CSV file not found"})

            csv_file_data = self.csv_files[file_id]
            file_path = csv_file_data['path']
            
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as csv_file:
                    csv_data = csv_file.read()
                    print("CSV Data:\n", csv_data)
                return send_from_directory(self.uploads_dir, os.path.basename(file_path), as_attachment=True)
            
            return jsonify({"status": "error", "message": "CSV file not found"})

        except Exception as e:
            return jsonify({"status": "error", "message": f"Error downloading CSV: {e}"}), 500

    def csv_acknowledgment(self, file_id):
        """
        Handles acknowledgment of CSV file transmission.

        Parameters:
            file_id (str): Unique identifier for the file.

        Returns:
            dict: JSON data indicating the status of the acknowledgment.
        """
        if file_id in self.file_info:
            self.file_info[file_id]['csv_sent'] = True
            return jsonify({"status": "success", "message": "CSV is sent to the React successfully"})
        
        return jsonify({"status": "error", "message": "File ID not found"})

app_server = AppServer(app)

if __name__ == '__main__':
    app_server.app.run(host='0.0.0.0', port=5001, debug=True)
