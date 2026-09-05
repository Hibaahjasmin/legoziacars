import json
import os
from datetime import datetime, timedelta

from dotenv import load_dotenv
from flask import (
    Flask,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
from werkzeug.middleware.proxy_fix import ProxyFix
import cloudinary
import cloudinary.uploader

# --- APP INITIALIZATION ---
app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

# Absolute Paths & Single Environment Load
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# --- CLOUDINARY CONFIGURATION ---
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# --- CONFIGURATIONS ---
app.secret_key = os.getenv('SECRET_KEY', 'autoheads_super_secure_vault_key_2026')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max payload limit

# Database Configuration (Supabase in production, local fallback)
db_url = os.getenv('DATABASE_URL')
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url or f"sqlite:///{os.path.join(BASE_DIR, 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# File Extensions
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}

# --- EMAIL CONFIGURATION ---
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 465))
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'True').lower() in ['true', '1']
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME', 'hibajasmin852@gmail.com')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD', 'wueazvourvltrgdt')
NOTIFICATION_EMAIL = os.getenv('NOTIFICATION_EMAIL', app.config['MAIL_USERNAME'])

mail = Mail(app)
socketio = SocketIO(app, cors_allowed_origins="*")
db = SQLAlchemy(app)

# --- ENVIRONMENT VARIABLES FOR AUTH WITH FALLBACKS ---
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "Legoziacars")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Jafarbasi@2026")


# -----------------------------------------------------------------
# DATABASE MODELS
# -----------------------------------------------------------------

class Car(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    brand = db.Column(db.String(100), default='N/A')
    model = db.Column(db.String(100), default='N/A')
    year = db.Column(db.String(20), default='N/A')
    mileage = db.Column(db.String(50), default='N/A')
    fuel = db.Column(db.String(50), default='N/A')
    transmission = db.Column(db.String(50), default='N/A')
    price = db.Column(db.String(50), default='N/A')
    description = db.Column(db.Text, default='')

    images = db.relationship('CarImage', backref='car', lazy=True, cascade='all, delete-orphan')


class CarImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    image_path = db.Column(db.String(550), nullable=False)
    car_id = db.Column(db.Integer, db.ForeignKey('car.id'), nullable=False)


class Inquiry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(100), default='General Inquiry')
    name = db.Column(db.String(150), default='Anonymous Lead')
    phone = db.Column(db.String(50), default='N/A')
    email = db.Column(db.String(150), default='N/A')
    place = db.Column(db.String(100), default='N/A')

    brand = db.Column(db.String(100))
    car_model = db.Column(db.String(100))
    variant = db.Column(db.String(100))
    year = db.Column(db.Integer)
    km_driven = db.Column(db.String(50))
    fuel_type = db.Column(db.String(50))
    transmission = db.Column(db.String(50))
    owners = db.Column(db.String(50))
    registration_number = db.Column(db.String(50))
    expected_amount = db.Column(db.String(50))

    overall_condition = db.Column(db.String(50))
    accident_history = db.Column(db.String(50))
    service_history = db.Column(db.String(50))

    message = db.Column(db.Text, default='')
    car_name = db.Column(db.String(200), default='')
    est_emi = db.Column(db.String(50), default='')
    images = db.Column(db.Text, default='')
    timestamp = db.Column(db.String(100))


with app.app_context():
    db.create_all()


# --- UTILITY HELPERS ---
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# -----------------------------------------------------------------
# ERROR HANDLERS & SEO ROUTES
# -----------------------------------------------------------------

@app.errorhandler(413)
def request_entity_too_large(error):
    flash("File upload exceeds the 16MB maximum allowed size limit.", "error")
    return redirect(request.referrer or url_for('admin_dashboard'))


@app.route('/sitemap.xml', methods=['GET'])
def sitemap():
    cars = Car.query.all()
    base_url = os.getenv('DOMAIN_NAME', 'https://legoziacars.com')
    
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_content += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for page in ['', '/sell', '/about']:
        xml_content += f'  <url><loc>{base_url}{page}</loc><changefreq>weekly</changefreq></url>\n'
        
    for car in cars:
        xml_content += f'  <url><loc>{base_url}/car/{car.id}</loc><changefreq>daily</changefreq></url>\n'
        
    xml_content += '</urlset>'
    
    return app.response_class(xml_content, mimetype='application/xml')


# -----------------------------------------------------------------
# CORE OPERATIONAL ROUTES
# -----------------------------------------------------------------

@app.route('/')
def home():
    stats = {
        "cars_sold": "1,450+", 
        "brands": "45+", 
        "satisfaction": "99%", 
        "experience": "12+"
    }
    cars = Car.query.all()
    
    cars_data = [{
        'id': c.id,
        'brand': c.brand,
        'model': c.model,
        'year': c.year,
        'mileage': c.mileage,
        'fuel': c.fuel,
        'transmission': c.transmission,
        'price': c.price,
        'description': c.description,
        'images': [img.image_path for img in c.images]
    } for c in cars]

    return render_template('index.html', cars=cars, cars_data=cars_data, stats=stats)


@app.route('/inventory')
def inventory():
    return redirect(url_for('home'))


@app.route('/sell', endpoint='sell_car', methods=['GET', 'POST'])
@app.route('/sell_car', methods=['GET', 'POST'])
def sell_car():
    if request.method == 'POST':
        uploaded_files = request.files.getlist('photos')
        saved_image_paths = []

        for idx, file in enumerate(uploaded_files):
            if file and allowed_file(file.filename):
                try:
                    upload_res = cloudinary.uploader.upload(file)
                    saved_image_paths.append(upload_res['secure_url'])
                except Exception as e:
                    print(f"Cloudinary upload error: {e}")

        brand = request.form.get('brand', '').strip()
        car_model = request.form.get('car_model', '').strip()
        year_val = request.form.get('year', '').strip()
        km_driven = request.form.get('km_driven', '').strip()

        name = request.form.get('name', 'Anonymous Lead').strip()
        phone = request.form.get('phone', 'N/A').strip()
        email = request.form.get('email', 'N/A').strip()
        expected_amount = request.form.get('expected_amount', 'N/A').strip()

        new_lead = Inquiry(
            type='Sell Request',
            name=name,
            email=email,
            phone=phone,
            place=request.form.get('place', 'N/A').strip(),
            brand=brand,
            car_model=car_model,
            variant=request.form.get('variant', '').strip(),
            year=int(year_val) if year_val.isdigit() else None,
            km_driven=km_driven,
            fuel_type=request.form.get('fuel_type', '').strip(),
            transmission=request.form.get('transmission', '').strip(),
            owners=request.form.get('owners', '').strip(),
            registration_number=request.form.get('registration_number', '').strip(),
            expected_amount=expected_amount,
            overall_condition=request.form.get('overall_condition', '').strip(),
            accident_history=request.form.get('accident_history', '').strip(),
            service_history=request.form.get('service_history', '').strip(),
            message=request.form.get('message', '').strip(),
            car_name=f'{year_val} {brand} {car_model}'.strip(),
            est_emi=f'Mileage: {km_driven}' if km_driven else '',
            images=','.join(saved_image_paths),
            timestamp=datetime.now().isoformat(),
        )

        db.session.add(new_lead)
        db.session.commit()

        socketio.emit('new_inquiry', {
            'title': 'New Car Sell Request!',
            'message': f'New valuation offer received for {year_val} {brand} {car_model}. Contact: {phone}'
        })

        try:
            msg = Message(
                subject=f'🚀 NEW SELL REQUEST: {year_val} {brand} {car_model}',
                sender=app.config['MAIL_USERNAME'],
                recipients=[NOTIFICATION_EMAIL],
            )
            msg.body = f"""
            🔥 NEW VEHICLE VALUATION REQUEST RECEIVED!
            
            CUSTOMER DETAILS:
            • Name: {name}
            • Phone: {phone}
            • Email: {email}
            
            VEHICLE DETAILS:
            • Vehicle: {year_val} {brand} {car_model}
            • KM Driven: {km_driven}
            • Expected Price: ₹{expected_amount}
            """
            mail.send(msg)
        except Exception as e:
            print(f'Email send error: {e}')

        flash('Your vehicle evaluation request has been submitted! Our team will contact you soon.')
        return redirect(url_for('sell_car'))

    return render_template('sell.html')


@app.route('/submit_sell_car', methods=['POST'])
def submit_sell_car():
    car_name = request.form.get('car_name', 'Vehicle')
    phone = request.form.get('phone', 'N/A')

    socketio.emit('new_inquiry', {
        'title': 'New Car Inquiry!',
        'message': f'New offer received for {car_name}. Contact: {phone}'
    })

    return jsonify({"status": "success", "message": "Inquiry submitted successfully"})


@app.route('/car/<int:car_id>')
def share_car(car_id):
    car = Car.query.get_or_404(car_id)
    primary_image = 'static/lego.png'

    if car.images:
        if isinstance(car.images, str):
            try:
                parsed_imgs = json.loads(car.images)
                primary_image = parsed_imgs[0]
            except Exception:
                primary_image = car.images.split(',')[0]
        elif isinstance(car.images, list):
            first_item = car.images[0]
            if isinstance(first_item, str):
                primary_image = first_item
            elif hasattr(first_item, 'image_path'):
                primary_image = first_item.image_path
            elif hasattr(first_item, 'filename'):
                primary_image = first_item.filename
            elif hasattr(first_item, 'url'):
                primary_image = first_item.url
            else:
                primary_image = str(first_item)

    primary_image = str(primary_image).strip()
    if not primary_image.startswith(('http://', 'https://')):
        primary_image = primary_image.lstrip('/')
        if not primary_image.startswith('static/'):
            primary_image = f'static/{primary_image}'

    return render_template('car_share.html', car=car, primary_image=primary_image)


@app.route('/submit-inquiry', methods=['POST'])
def submit_inquiry():
    name = request.form.get('name', 'Anonymous Lead').strip()
    phone = request.form.get('phone', 'N/A').strip()
    email = request.form.get('email', 'N/A').strip()
    car_name = request.form.get('car_name', '').strip()
    message_text = request.form.get('message', '').strip()
    inquiry_type = request.form.get('type', 'General Inquiry').strip()

    new_lead = Inquiry(
        type=inquiry_type,
        name=name,
        phone=phone,
        email=email,
        message=message_text,
        car_name=car_name,
        est_emi=request.form.get('est_emi', '').strip(),
        timestamp=datetime.now().isoformat(),
    )

    db.session.add(new_lead)
    db.session.commit()

    socketio.emit('new_inquiry', {
        'title': 'New Inquiry Received!',
        'message': f'Inquiry from {name} regarding {car_name if car_name else "a vehicle"}. Contact: {phone}',
    })

    try:
        msg = Message(
            subject=f'📥 NEW INQUIRY: {car_name if car_name else "General Customer Inquiry"}',
            sender=app.config['MAIL_USERNAME'],
            recipients=[NOTIFICATION_EMAIL],
        )
        msg.body = f"""
        📩 NEW CUSTOMER INQUIRY!
        
        • Type: {inquiry_type}
        • Name: {name}
        • Phone: {phone}
        • Email: {email}
        • Interested Car: {car_name if car_name else 'N/A'}
        • Message: {message_text}
        """
        mail.send(msg)
    except Exception as e:
        print(f'Email send error: {e}')

    flash('Inquiry sent!')
    return redirect(url_for('home'))


# -----------------------------------------------------------------
# ADMINISTRATIVE & MANAGEMENT ROUTES
# -----------------------------------------------------------------

@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    cars = Car.query.all()
    inquiries = Inquiry.query.order_by(Inquiry.id.desc()).all()
    car_inquiries = Inquiry.query.filter_by(type='Sell Request').order_by(Inquiry.id.desc()).all()
    
    return render_template('admin.html', cars=cars, inquiries=inquiries, car_inquiries=car_inquiries)


@app.route('/admin/add', methods=['POST'])
def add_car():
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    uploaded_files = request.files.getlist('photos')
    
    new_car = Car(
        brand=request.form.get('brand', 'N/A').strip(),
        model=request.form.get('model', 'N/A').strip(),
        year=request.form.get('year', 'N/A').strip(),
        mileage=request.form.get('mileage', 'N/A').strip() if request.form.get('mileage') else 'N/A',
        fuel=request.form.get('fuel', 'N/A') if request.form.get('fuel') else 'N/A',
        transmission=request.form.get('transmission', 'N/A') if request.form.get('transmission') else 'N/A',
        price=request.form.get('price', 'N/A').strip() if request.form.get('price') else 'N/A',
        description=request.form.get('description', '').strip()
    )
    db.session.add(new_car)
    db.session.flush() 
    
    for idx, file in enumerate(uploaded_files):
        if file and allowed_file(file.filename):
            try:
                upload_res = cloudinary.uploader.upload(file)
                img_entry = CarImage(
                    image_path=upload_res['secure_url'],
                    car_id=new_car.id
                )
                db.session.add(img_entry)
            except Exception as e:
                print(f"Cloudinary upload error: {e}")

    db.session.commit()
    flash("Vehicle added successfully!")
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete/<int:car_id>', methods=['POST'])
def delete_car(car_id):
    if not session.get('logged_in'): 
        return redirect(url_for('login'))
    
    car_to_delete = Car.query.get(car_id)
    if car_to_delete:
        for img in car_to_delete.images:
            if not img.image_path.startswith(('http://', 'https://')):
                file_path = os.path.join(app.root_path, 'static', img.image_path)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Failed to delete file {file_path}: {e}")

        db.session.delete(car_to_delete)
        db.session.commit()
        flash("Vehicle and associated image records deleted successfully!")
        
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/inquiry/publish/<int:id>', methods=['POST'], endpoint='publish_inquiry')
def publish_inquiry(id):
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    inquiry = Inquiry.query.get_or_404(id)
    
    if inquiry.images:
        for relative_path in inquiry.images.split(','):
            relative_path = relative_path.strip()
            if relative_path and not relative_path.startswith(('http://', 'https://')):
                file_path = os.path.join(app.root_path, relative_path)
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception as e:
                        print(f"Failed to delete inquiry file {file_path}: {e}")

    db.session.delete(inquiry)
    db.session.commit()
    flash("Inquiry dismissed.")
    return redirect(url_for('admin_dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        env_admin_user = os.getenv('ADMIN_USERNAME', '')
        env_admin_pass = os.getenv('ADMIN_PASSWORD', '')
        
        if username.lower() == env_admin_user.lower() and password == env_admin_pass:
            session.permanent = True
            session['logged_in'] = True
            session['user_role'] = 'admin'
            flash("Logged in successfully!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            flash("Invalid administrative credentials sequence.", "error")
            
    return render_template('login.html')

@app.route('/about')
def about_page():
    return render_template('about.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('user_role', None)
    flash("Logged out successfully.", "info")
    return redirect(url_for('home'))


@app.route('/robots.txt')
def robots():
    base_url = os.getenv('DOMAIN_NAME', request.url_root.rstrip('/'))
    content = f"User-agent: *\nDisallow: /admin\nAllow: /\nSitemap: {base_url}/sitemap.xml"
    return app.response_class(content, mimetype='text/plain')


if __name__ == '__main__':
    socketio.run(app, debug=True, port=5000, host="0.0.0.0")