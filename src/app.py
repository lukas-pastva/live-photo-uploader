from flask import Flask, render_template, request, redirect, url_for, send_from_directory, send_file, abort, jsonify
import os
import shutil
from PIL import Image
import pyheif
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge
import io
import zipfile

app = Flask(__name__)

# Configurable upload directory via environment variable
UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configurable image quality via environment variable
# Default quality is 100
IMAGE_QUALITY = int(os.environ.get('IMAGE_QUALITY', '100'))

# Configurable thumbnail quality (percentage)
THUMBNAIL_QUALITY = 85

# Set maximum upload size to 5GB (adjust as needed)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5 GB

# Ensure the upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'heic', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'mp4', 'mov', 'avi', 'mkv'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_file(filepath, category):
    filename = os.path.basename(filepath)
    name, ext = os.path.splitext(filename)
    ext = ext.lower()

    # Check if the file is an image or video
    image_extensions = {'.heic', '.jpg', '.jpeg', '.png', '.gif', '.bmp'}
    video_extensions = {'.mp4', '.mov', '.avi', '.mkv'}

    if ext not in image_extensions and ext not in video_extensions:
        # Unsupported file type
        return

    if ext in video_extensions:
        # For videos, no processing is needed
        # Copy the video file to the 'largest' directory to keep consistency
        save_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, 'largest')
        os.makedirs(save_dir, exist_ok=True)
        save_path = os.path.join(save_dir, filename)
        shutil.copyfile(filepath, save_path)
        # No further processing needed
        return

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
        # Since HEIC is not widely supported, we'll convert it to JPEG
        original_format = 'JPEG'
        save_extension = '.jpeg'
    else:
        # Open other image formats
        image = Image.open(filepath)
        original_format = image.format  # Get the original image format
        save_extension = ext  # Use the original file extension

    # Handle images with transparency (alpha channel)
    if image.mode in ('RGBA', 'LA'):
        # Create a white background image
        background = Image.new('RGB', image.size, (255, 255, 255))
        # Paste the original image onto the background using the alpha channel as a mask
        background.paste(image, mask=image.split()[-1])  # Use the alpha channel as mask
        image = background  # Update the image variable to the new image without alpha
        original_format = 'JPEG'  # Save as JPEG since transparency is removed
        save_extension = '.jpeg'
    elif image.mode != 'RGB':
        # Convert image to 'RGB' mode if it's not already
        image = image.convert('RGB')

    # Define the sizes for different resolutions
    sizes = {
        'largest': (2880, 1620),
        'medium': (1920, 1080),
        'thumbnail': (400, 400),
    }

    # Generate and save images in different resolutions
    for size_name, size in sizes.items():
        img_copy = image.copy()
        if size_name == 'largest':
            # Only resize if the image is larger than the target size
            if image.width > size[0] or image.height > size[1]:
                img_copy.thumbnail(size)
            # Save the image in the appropriate format with maximum quality
            save_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, size_name)
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f'{name}{save_extension}')
            img_copy.save(save_path, original_format, quality=100)
        elif size_name == 'medium':
            # Resize to the target size
            img_copy.thumbnail(size)
            # Save as JPEG with default image quality
            save_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, size_name)
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f'{name}.jpeg')
            img_copy.save(save_path, 'JPEG', quality=IMAGE_QUALITY)
        elif size_name == 'thumbnail':
            # Resize to the target size
            img_copy.thumbnail(size)
            # Save as JPEG with reduced quality
            save_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, size_name)
            os.makedirs(save_dir, exist_ok=True)
            save_path = os.path.join(save_dir, f'{name}.jpeg')
            img_copy.save(save_path, 'JPEG', quality=THUMBNAIL_QUALITY)

@app.route('/')
def index():
    categories = os.listdir(app.config['UPLOAD_FOLDER'])
    return render_template('index.html', categories=categories)

@app.route('/category/<category>')
def category_view(category):
    # Get filenames from the 'largest' directory
    largest_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, 'largest')
    if os.path.exists(largest_dir):
        files = os.listdir(largest_dir)
        file_info_list = []
        for file in files:
            name, ext = os.path.splitext(file)
            ext = ext.lower()
            file_info_list.append({'name': name, 'ext': ext, 'filename': file})
    else:
        file_info_list = []
    return render_template('category.html', category=category, files=file_info_list)

@app.route('/category/create', methods=['POST'])
def create_category():
    category = request.form.get('category_name')
    if category:
        # Sanitize category name
        category = secure_filename(category)
        category_path = os.path.join(app.config['UPLOAD_FOLDER'], category)
        os.makedirs(category_path, exist_ok=True)
        # Create subdirectories
        for sub_dir in ['source', 'largest', 'medium', 'thumbnail']:
            os.makedirs(os.path.join(category_path, sub_dir), exist_ok=True)
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
            return jsonify({'status': 'fail', 'message': 'No file part'}), 400
        files = request.files.getlist('photos[]')
        if not files or files[0].filename == '':
            return jsonify({'status': 'fail', 'message': 'No selected files'}), 400
        for file in files:
            if file and allowed_file(file.filename):
                # Use secure filename
                filename = secure_filename(file.filename)
                # Save the original file
                category_path = os.path.join(app.config['UPLOAD_FOLDER'], category, 'source')
                os.makedirs(category_path, exist_ok=True)
                filepath = os.path.join(category_path, filename)
                file.save(filepath)

                # Process the file
                process_file(filepath, category)
        return jsonify({'status': 'success', 'message': 'Files uploaded successfully.'}), 200
    return render_template('upload.html', category=category)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/download_category/<category>')
def download_category(category):
    # Get the size parameter from the query string
    size = request.args.get('size', 'largest')

    # Validate the size parameter
    valid_sizes = ['source', 'largest', 'medium']
    if size not in valid_sizes:
        return jsonify({'status': 'fail', 'message': 'Invalid size parameter.'}), 400

    # Path to the directory containing the images of the specified size
    images_dir = os.path.join(app.config['UPLOAD_FOLDER'], category, size)
    if not os.path.exists(images_dir):
        return jsonify({'status': 'fail', 'message': 'Size not found.'}), 404

    # Collect all image file paths
    image_filenames = os.listdir(images_dir)
    image_paths = [os.path.join(images_dir, filename) for filename in image_filenames]

    if not image_filenames:
        return jsonify({'status': 'fail', 'message': 'No files to download.'}), 404

    # Create a ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
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
        download_name=f'{category}_{size}_files.zip'
    )

@app.route('/delete_photo/<category>/<filename>', methods=['POST'])
def delete_photo(category, filename):
    # Define all sizes to delete
    sizes = ['source', 'largest', 'medium', 'thumbnail']
    success = True
    messages = []

    for size in sizes:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], category, size, filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                success = False
                messages.append(f'Error deleting {size} version: {str(e)}')
        else:
            # File does not exist
            pass  # You can choose to add a message if desired

    if success:
        return jsonify({'status': 'success', 'message': f"'{filename}' has been deleted successfully."}), 200
    else:
        return jsonify({'status': 'fail', 'message': ' '.join(messages)}), 500

@app.route('/download_single/<category>/<size>/<filename>')
def download_single(category, size, filename):
    # Validate size
    valid_sizes = ['source', 'largest', 'medium', 'thumbnail']
    if size not in valid_sizes:
        abort(404)

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], category, size, filename)
    if not os.path.exists(file_path):
        abort(404)

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename
    )

@app.errorhandler(RequestEntityTooLarge)
def handle_file_size_error(e):
    return jsonify({'status': 'fail', 'message': 'File too large. Maximum upload size is 5GB.'}), 413

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
