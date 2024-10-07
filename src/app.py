from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file, abort, Response
import os
import shutil
from PIL import Image
import pyheif
import uuid
from werkzeug.utils import secure_filename
import io
import zipfile
from flask import send_file

app = Flask(__name__)

# Configurable upload directory via environment variable
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configurable image quality via environment variable
# Default quality is 100
IMAGE_QUALITY = int(os.environ.get('IMAGE_QUALITY', '100'))

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

    # Open the image file
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

    # Handle images with transparency (alpha channel)
    if image.mode in ('RGBA', 'LA'):
        # Create a white background image
        background = Image.new('RGB', image.size, (255, 255, 255))
        # Paste the original image onto the background using the alpha channel as a mask
        background.paste(image, mask=image.split()[3])  # Split to get the alpha channel
        image = background  # Update the image variable to the new image without alpha
    elif image.mode != 'RGB':
        # Convert image to 'RGB' mode if it's not already
        image = image.convert('RGB')

    # Define the sizes for different resolutions
    sizes = {
        'largest': (1920, 1080),
        'medium': (1280, 720),
        'thumbnail': (200, 200),
    }

    # Generate and save images in different resolutions
    for size_name, size in sizes.items():
        img_copy = image.copy()
        img_copy.thumbnail(size)
        save_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, size_name)
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, f'{name}.jpeg')
        # Save the image with the specified quality
        img_copy.save(save_path, 'JPEG', quality=IMAGE_QUALITY)

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
        if 'photos[]' not in request.files:
            return 'No file part', 400
        files = request.files.getlist('photos[]')
        if not files or files[0].filename == '':
            return 'No selected files', 400
        for file in files:
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

@app.route('/download_category/<category>')
def download_category(category):
    # Path to the directory containing the images (choose desired size)
    images_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, 'largest')
    if not os.path.exists(images_dir):
        return 'Category not found', 404

    # Collect all image file paths
    image_filenames = os.listdir(images_dir)
    image_paths = [os.path.join(images_dir, filename) for filename in image_filenames]

    # Create a ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for file_path, filename in zip(image_paths, image_filenames):
            # Add each file to the ZIP archive
            zip_file.write(file_path, arcname=filename)

    # Set the pointer to the beginning of the stream
    zip_buffer.seek(0)

    # Send the ZIP file as a response
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'{category}_photos.zip'
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
