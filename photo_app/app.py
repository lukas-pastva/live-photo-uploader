from flask import Flask, render_template, request, redirect, url_for
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'heic', 'jpg', 'jpeg', 'png', 'mov', 'mp4'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload/<category>', methods=['GET', 'POST'])
def upload_file(category):
    if request.method == 'POST':
        # Check if the post request has the file part
        if 'photo' not in request.files:
            return 'No file part', 400
        file = request.files['photo']
        if file.filename == '':
            return 'No selected file', 400
        if file and allowed_file(file.filename):
            # Save the original file
            category_path = os.path.join(app.config['UPLOAD_FOLDER'], category, 'source')
            os.makedirs(category_path, exist_ok=True)
            filepath = os.path.join(category_path, file.filename)
            file.save(filepath)

            # Process the file
            process_file(filepath, category)

            return redirect(url_for('category_view', category=category))
    return render_template('upload.html', category=category)
