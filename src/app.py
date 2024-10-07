from flask import Flask, render_template, request, redirect, url_for, send_from_directory
import os
import shutil
from PIL import Image
import pyheif

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'heic', 'jpg', 'jpeg', 'png', 'mov', 'mp4'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_file(filepath, category):
    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext == '.heic':
        # Read HEIC file
        heif_file = pyheif.read(filepath)
        image = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw",
            heif_file.mode,
            heif_file.stride,
        )
    else:
        # Open other image formats
        image = Image.open(filepath)

    # Handle images with alpha channel
    if image.mode in ('RGBA', 'LA'):
        # Create a white background
        background = Image.new('RGB', image.size, (255, 255, 255))
        # Paste the image onto the background using the alpha channel as a mask
        background.paste(image, mask=image.split()[3])  # 3 is the alpha channel
        image = background
    elif image.mode != 'RGB':
        # Convert image to RGB if it's in a different mode
        image = image.convert('RGB')

    # Generate different resolutions
    sizes = {
        'largest': (1920, 1080),
        'medium': (1280, 720),
        'thumbnail': (200, 200),
    }

    for size_name, size in sizes.items():
        img_copy = image.copy()
        img_copy.thumbnail(size)
        save_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, size_name)
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f'{name}.jpeg')
        img_copy.save(save_path, 'JPEG')


@app.route('/')
def index():
    categories = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', categories=categories)

@app.route('/category/<category>')
def category_view(category):
    # Display images in the category
    thumbnails_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, 'thumbnail')
    images = os.listdir(thumbnails_dir) if os.path.exists(thumbnails_dir) else []
    return render_template('category.html', category=category, images=images)

@app.route('/category/create', methods=['POST'])
def create_category():
    category = request.form.get('category_name')
    if category:
        category_path = os.path.join(app.config['UPLOAD_FOLDER'], category)
        os.makedirs(category_path, exist_ok=True)
    return redirect(url_for('index'))

@app.route('/category/delete/<category>', methods=['POST'])
def delete_category(category):
    category_path = os.path.join(app.config['UPLOAD_FOLDER'], category)
    if os.path.exists(category_path):
        shutil.rmtree(category_path)
    return redirect(url_for('index'))

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

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(debug=True)
