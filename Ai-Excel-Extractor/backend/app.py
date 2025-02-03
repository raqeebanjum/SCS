from flask import Flask, request, jsonify, send_file, send_from_directory
import os
import json
import pandas as pd
import logging
from pathlib import Path
from src.excel_parser.excel_parser import ExcelParser
from src.ai.ollama_handler import process_data
import uuid
from flask_cors import CORS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask with static folder
app = Flask(__name__, static_folder='static') 
CORS(app)
app.secret_key = os.urandom(24)

app.config.update({
    'UPLOAD_FOLDER': 'temp/',
    'MAX_CONTENT_LENGTH': 50 * 1024 * 1024,
    'OLLAMA_MODEL': 'mistral',
    'OLLAMA_HOST': os.getenv('OLLAMA_HOST', 'localhost')
})
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Serve React App - Main HTML
@app.route('/')
def serve():
    return send_from_directory(app.static_folder, 'index.html')

# Serve React App - Static Files (JS, CSS, etc.)
@app.route('/<path:path>')
def static_files(path):
    return send_from_directory(app.static_folder, path)

@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
            
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and file.filename.endswith('.xlsx'):
        # Generate unique ID for this upload
        upload_id = str(uuid.uuid4())
        temp_path = Path(app.config['UPLOAD_FOLDER']) / f"{upload_id}.xlsx"
        file.save(temp_path)
        
        # Get sheet names
        sheet_names = ExcelParser.get_sheet_names(str(temp_path))
        
        return jsonify({
            'upload_id': upload_id,
            'sheet_names': sheet_names
        })

    return jsonify({'error': 'Invalid file type'}), 400

@app.route('/api/process', methods=['POST'])
def process():
    temp_excel = None
    json_file = None
    output_excel = None
    try:
        upload_id = request.form['upload_id']
        temp_excel = Path(app.config['UPLOAD_FOLDER']) / f"{upload_id}.xlsx"
        
        if not temp_excel.exists():
            return jsonify({'error': 'Invalid file session'}), 400

        # Create file paths
        json_file = temp_excel.with_name(f"{upload_id}.json")
        output_excel = temp_excel.with_name(f"{upload_id}_processed.xlsx")

        # Excel to JSON conversion
        parser = ExcelParser(str(temp_excel))
        if not parser.load_file(sheet_name=request.form['sheet_name']):
            return jsonify({'error': 'Invalid sheet name'}), 400
        
        # Get basic data
        extracted_data = parser.extract_data(
            request.form['part_cell'], 
            request.form['desc_cell']
        )
        
        # Process data through AI
        processed_data = process_data(extracted_data)
        
        # Save processed JSON (temporary)
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(processed_data, f, indent=2, ensure_ascii=False)
        
        # Convert processed data to Excel
        df = pd.DataFrame(processed_data)
        
        # Define columns order (excluding excel_row)
        columns = [
            'part_number',
            'description',
            'Size',
            'Length',
            'Height',
            'Flange Class',
            'Pipe Class',
            'Manufacturer',
            'Connection Type 1',
            'Connection Type 2',
            'Product Type',
            'Body Material',
            'Trim Material',
            'Seat/Elastomer material',
            'NACE (Y/N)',
            'Fireproof (Y/N)',
            'API (Y/N)',
            'ASME (Y/N)',
            'Operation',
            'Mfr Model Number',
            'Vendor Material Number',
            'Meter Type',
            'Perforation Size',
            'Orifice Diameter',
            'Pump Type',
            'Horsepower',
            'RPM',
            'Phase',
            'Voltage',
            'Hertz',
            'Class 1 Division',
            'NEMA',
            'Specific Gravity',
            'Pressure',
            'Flow Rate',
            'Temperature',
            'Other'
        ]
        
        # Reorder columns and fill missing columns with empty strings
        for col in columns:
            if col not in df.columns:
                df[col] = ''
                
        # Select only the columns we want in the order we want
        df = df[columns]
        
        # Save to Excel
        df.to_excel(output_excel, index=False)
        logger.info(f"Generated Excel file at {output_excel}")

        # Send the Excel file
        return send_file(
            output_excel,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='processed_results.xlsx'
        )

    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        return jsonify({'error': str(e)}), 500
        
    finally:
        # Clean up temporary files
        for file in [temp_excel, json_file, output_excel]:
            if file and file.exists():
                try:
                    file.unlink()
                    logger.info(f"Cleaned up {file.name}")
                except Exception as e:
                    logger.error(f"Error cleaning up {file.name}: {str(e)}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)