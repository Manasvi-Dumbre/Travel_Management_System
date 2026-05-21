from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_socketio import SocketIO, emit
from werkzeug.utils import secure_filename
import os
import sqlite3
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this to a secure key
app.config['UPLOAD_FOLDER'] = 'static/hotel_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
socketio = SocketIO(app, async_mode='threading')

# Add these constants after app initialization
AIRPORTS = {
    'DEL': {'name': 'Delhi International Airport', 'city': 'Delhi'},
    'BOM': {'name': 'Mumbai International Airport', 'city': 'Mumbai'},
    'BLR': {'name': 'Bengaluru International Airport', 'city': 'Bengaluru'},
    'HYD': {'name': 'Hyderabad International Airport', 'city': 'Hyderabad'},
    'CCU': {'name': 'Kolkata International Airport', 'city': 'Kolkata'},
    'MAA': {'name': 'Chennai International Airport', 'city': 'Chennai'},
    'GOI': {'name': 'Goa International Airport', 'city': 'Goa'},
    'JAI': {'name': 'Jaipur International Airport', 'city': 'Jaipur'},
    'IXC': {'name': 'Chandigarh International Airport', 'city': 'Chandigarh'},
    'AMD': {'name': 'Ahmedabad International Airport', 'city': 'Ahmedabad'}
}

TRAIN_STATIONS = {
    'NDLS': {'name': 'New Delhi Railway Station', 'city': 'Delhi'},
    'CSMT': {'name': 'Mumbai CSMT', 'city': 'Mumbai'},
    'SBC': {'name': 'Bengaluru City Junction', 'city': 'Bengaluru'},
    'SCB': {'name': 'Secunderabad Junction', 'city': 'Hyderabad'},
    'KOAA': {'name': 'Kolkata Railway Station', 'city': 'Kolkata'},
    'MAS': {'name': 'Chennai Central', 'city': 'Chennai'},
    'MAO': {'name': 'Madgaon Junction', 'city': 'Goa'},
    'JP': {'name': 'Jaipur Junction', 'city': 'Jaipur'},
    'CDG': {'name': 'Chandigarh Railway Station', 'city': 'Chandigarh'},
    'ADI': {'name': 'Ahmedabad Junction', 'city': 'Ahmedabad'}
}

def calculate_price(origin, destination, mode='flight'):
    # More realistic base pricing
    base_price = 4500 if mode == 'flight' else 1200
    
    # Updated city pairs with more realistic multipliers
    city_pairs = {
        ('Delhi', 'Mumbai'): 1.8,      # ~8100 flight / 2160 train
        ('Delhi', 'Bengaluru'): 2.2,   # ~9900 flight / 2640 train
        ('Delhi', 'Chennai'): 2.3,     # ~10350 flight / 2760 train
        ('Delhi', 'Kolkata'): 1.7,     # ~7650 flight / 2040 train
        ('Delhi', 'Goa'): 2.1,         # ~9450 flight / 2520 train
        ('Mumbai', 'Bengaluru'): 1.4,  # ~6300 flight / 1680 train
        ('Mumbai', 'Chennai'): 1.5,    # ~6750 flight / 1800 train
        ('Mumbai', 'Kolkata'): 2.0,    # ~9000 flight / 2400 train
        ('Mumbai', 'Goa'): 0.8,        # ~3600 flight / 960 train
        ('Bengaluru', 'Chennai'): 0.7, # ~3150 flight / 840 train
        ('Bengaluru', 'Kolkata'): 1.9, # ~8550 flight / 2280 train
        ('Chennai', 'Kolkata'): 1.8,   # ~8100 flight / 2160 train
        ('Jaipur', 'Delhi'): 0.7,      # ~3150 flight / 840 train
        ('Ahmedabad', 'Mumbai'): 0.9,  # ~4050 flight / 1080 train
        ('Chandigarh', 'Delhi'): 0.6   # ~2700 flight / 720 train
    }

    cities = sorted([origin, destination])
    multiplier = city_pairs.get(tuple(cities), 1.8)  # Default multiplier for unlisted routes
    
    # Add slight random variation (±5%) to make prices more realistic
    variation = 0.95 + (hash(f"{origin}{destination}") % 100) / 1000
    return round(base_price * multiplier * variation, -2)  # Round to nearest 100

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database initialization
def check_db_exists():
    return os.path.exists('travel.db')

def init_db():
    if not check_db_exists():
        print("Database not found. Creating new database...")
        
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    try:
        # Create tables
        c.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                is_admin INTEGER DEFAULT 0
            );
            
            CREATE TABLE IF NOT EXISTS hotels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                location TEXT NOT NULL,
                price REAL NOT NULL,
                available_rooms INTEGER NOT NULL,
                image_path TEXT
            );
            
            CREATE TABLE IF NOT EXISTS flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                flight_number TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                price REAL NOT NULL,
                available_seats INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS trains (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                train_number TEXT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                price REAL NOT NULL,
                available_seats INTEGER NOT NULL
            );
            
            CREATE TABLE IF NOT EXISTS cart (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
            
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_type TEXT NOT NULL,
                item_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                booking_date TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );

            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        ''')
        conn.commit()
        
        if not check_db_exists():
            print("Database created successfully!")
    except sqlite3.Error as e:
        print(f"Error creating database: {e}")
        raise
    finally:
        conn.close()

# Add this function after init_db()
def create_admin():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    # Check if admin exists
    c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
    if c.fetchone() is None:
        # Create admin user with password 'admin123'
        admin_password = generate_password_hash('admin123')
        c.execute('INSERT INTO users (username, password, is_admin) VALUES (?, ?, 1)',
                 ('admin', admin_password))
        conn.commit()
    conn.close()

# Initialize database on startup
try:
    init_db()
    create_admin()
except Exception as e:
    print(f"Error initializing application: {e}")
    raise

# Login decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Admin decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            flash('Admin access required')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/explore/hotels')
def explore_hotels():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    c.execute('SELECT * FROM hotels')
    hotels = c.fetchall()
    conn.close()
    return render_template('explore_hotels.html', hotels=hotels)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        
        conn = sqlite3.connect('travel.db')
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, password) VALUES (?, ?)',
                     (username, password))
            conn.commit()
            flash('Registration successful')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = sqlite3.connect('travel.db')
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            session['is_admin'] = user[3]
            return redirect(url_for('home'))
        flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

@app.route('/currency-converter')
def currency_converter():
    return render_template('currency_converter.html')

@app.route('/translator')
def translator():
    return render_template('translator.html')

@app.route('/chat')
@login_required
def chat():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    c.execute('''
        SELECT m.id, m.username, m.message, m.timestamp 
        FROM chat_messages m 
        ORDER BY m.timestamp DESC 
        LIMIT 50
    ''')
    messages = c.fetchall()
    conn.close()
    return render_template('chat.html', messages=messages)

@socketio.on('send_message')
def handle_message(data):
    if 'user_id' not in session:
        return
    
    message = data.get('message')
    if message:
        conn = sqlite3.connect('travel.db')
        c = conn.cursor()
        try:
            c.execute('''
                INSERT INTO chat_messages (user_id, username, message, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (session['user_id'], session['username'], message, datetime.now()))
            conn.commit()
            
            # Emit message to all clients
            emit('new_message', {
                'username': session['username'],
                'message': message,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }, broadcast=True)
        except sqlite3.Error as e:
            print(f"Error saving message: {e}")
        finally:
            conn.close()

@app.route('/get_messages')
@login_required
def get_messages():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    c.execute('''
        SELECT id, username, message, timestamp 
        FROM chat_messages 
        ORDER BY timestamp DESC 
        LIMIT 50
    ''')
    messages = c.fetchall()
    conn.close()
    return jsonify([{
        'id': m[0],
        'username': m[1],
        'message': m[2],
        'timestamp': m[3]
    } for m in messages])

# Admin routes
@app.route('/admin')
@admin_required
def admin():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    # Fetch all items
    c.execute('SELECT * FROM hotels')
    hotels = c.fetchall()
    
    c.execute('SELECT * FROM flights')
    flights = c.fetchall()
    
    c.execute('SELECT * FROM trains')
    trains = c.fetchall()
    
    # Fetch all bookings with user details
    c.execute('''
        SELECT b.*, u.username,
        CASE b.item_type
            WHEN 'hotels' THEN h.name
            WHEN 'flights' THEN f.flight_number
            WHEN 'trains' THEN t.train_number
        END as item_name
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        LEFT JOIN hotels h ON b.item_id = h.id AND b.item_type = 'hotels'
        LEFT JOIN flights f ON b.item_id = f.id AND b.item_type = 'flights'
        LEFT JOIN trains t ON b.item_id = t.id AND b.item_type = 'trains'
        ORDER BY b.booking_date DESC
    ''')
    bookings = c.fetchall()
    
    conn.close()
    return render_template('admin.html', hotels=hotels, flights=flights, trains=trains, bookings=bookings)

@app.route('/admin/<item_type>', methods=['GET', 'POST'])
@admin_required
def manage_items(item_type):
    if request.method == 'POST' and item_type == 'hotels':
        conn = sqlite3.connect('travel.db')
        c = conn.cursor()
        
        # Handle image upload
        image_path = None
        if 'hotel_image' in request.files:
            file = request.files['hotel_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_path = f'hotel_images/{filename}'
        
        c.execute('''INSERT INTO hotels (name, location, price, available_rooms, image_path)
                    VALUES (?, ?, ?, ?, ?)''',
                 (request.form['name'], request.form['location'],
                  float(request.form['price']), int(request.form['available']),
                  image_path))
        
        conn.commit()
        conn.close()
        flash(f'{item_type.capitalize()} added successfully')
    
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    c.execute(f'SELECT * FROM {item_type}')
    items = c.fetchall()
    conn.close()
    
    return render_template('admin.html', 
                         items=items, 
                         item_type=item_type,
                         is_transport=(item_type in ['flights', 'trains']))

@app.route('/admin/delete/<item_type>/<int:item_id>')
@admin_required
def delete_item(item_type, item_id):
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    try:
        c.execute(f'DELETE FROM {item_type} WHERE id = ?', (item_id,))
        conn.commit()
        flash(f'{item_type.capitalize()} deleted successfully')
    except:
        flash('Error deleting item')
    
    conn.close()
    return redirect(url_for('admin'))

@app.route('/admin/bookings')
@admin_required
def manage_bookings():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT 
            b.id,
            b.booking_date,
            u.username,
            b.item_type,
            CASE b.item_type
                WHEN 'hotels' THEN h.name
                WHEN 'flights' THEN f.flight_number
                WHEN 'trains' THEN t.train_number
            END as item_name,
            CASE b.item_type
                WHEN 'hotels' THEN h.location
                WHEN 'flights' THEN f.origin || ' to ' || f.destination
                WHEN 'trains' THEN t.origin || ' to ' || t.destination
            END as location_info,
            b.quantity,
            CASE b.item_type
                WHEN 'hotels' THEN h.price
                WHEN 'flights' THEN f.price
                WHEN 'trains' THEN t.price
            END as price
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        LEFT JOIN hotels h ON b.item_id = h.id AND b.item_type = 'hotels'
        LEFT JOIN flights f ON b.item_id = f.id AND b.item_type = 'flights'
        LEFT JOIN trains t ON b.item_id = t.id AND b.item_type = 'trains'
        ORDER BY b.booking_date DESC
    ''')
    bookings = c.fetchall()
    conn.close()
    
    return render_template('admin_bookings.html', bookings=bookings)

@app.route('/admin/hotel-bookings')
@admin_required
def manage_hotel_bookings():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    c.execute('''
        SELECT 
            b.id,
            b.booking_date,
            u.username,
            h.name,
            h.location,
            b.quantity,
            COALESCE(h.price, 0) as price,
            COALESCE(b.quantity * h.price, 0) as total_price
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN hotels h ON b.item_id = h.id
        WHERE b.item_type = 'hotels'
        ORDER BY b.booking_date DESC
    ''')
    hotel_bookings = c.fetchall()
    conn.close()
    
    return render_template('admin_hotel_bookings.html', bookings=hotel_bookings)

@app.route('/admin/users')
@admin_required
def manage_users():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    # Get all users and their booking counts
    c.execute('''
        SELECT 
            u.id,
            u.username,
            u.is_admin,
            COUNT(DISTINCT b.id) as booking_count,
            SUM(CASE 
                WHEN b.item_type = 'hotels' THEN h.price * b.quantity
                WHEN b.item_type = 'flights' THEN f.price * b.quantity
                WHEN b.item_type = 'trains' THEN t.price * b.quantity
                ELSE 0
            END) as total_spent
        FROM users u
        LEFT JOIN bookings b ON u.id = b.user_id
        LEFT JOIN hotels h ON b.item_id = h.id AND b.item_type = 'hotels'
        LEFT JOIN flights f ON b.item_id = f.id AND b.item_type = 'flights'
        LEFT JOIN trains t ON b.item_id = t.id AND b.item_type = 'trains'
        GROUP BY u.id
        ORDER BY u.username
    ''')
    users = c.fetchall()
    conn.close()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin/toggle-admin/<int:user_id>')
@admin_required
def toggle_admin(user_id):
    if user_id != session['user_id']:  # Prevent self-demotion
        conn = sqlite3.connect('travel.db')
        c = conn.cursor()
        c.execute('UPDATE users SET is_admin = NOT is_admin WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
    return redirect(url_for('manage_users'))

@app.route('/admin/delete-user/<int:user_id>')
@admin_required
def delete_user(user_id):
    if user_id != session['user_id']:  # Prevent self-deletion
        conn = sqlite3.connect('travel.db')
        c = conn.cursor()
        try:
            # Delete user's bookings
            c.execute('DELETE FROM bookings WHERE user_id = ?', (user_id,))
            # Delete user's cart items
            c.execute('DELETE FROM cart WHERE user_id = ?', (user_id,))
            # Delete user
            c.execute('DELETE FROM users WHERE id = ?', (user_id,))
            conn.commit()
            flash('User deleted successfully')
        except:
            flash('Error deleting user')
        finally:
            conn.close()
    return redirect(url_for('manage_users'))

# Search routes
@app.route('/search/<item_type>')
def search(item_type):
    if item_type != 'hotels':
        return redirect(url_for('transport_search', mode=item_type))
        
    query = request.args.get('q', '')
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM hotels WHERE name LIKE ? OR location LIKE ?',
             (f'%{query}%', f'%{query}%'))
    
    results = c.fetchall()
    conn.close()
    return render_template('search.html', results=results, item_type=item_type)

# Cart routes
@app.route('/cart')
@login_required
def view_cart():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    c.execute('''SELECT 
                 c.id,
                 c.user_id,
                 c.item_type,
                 c.item_id,
                 c.quantity,
                 CASE c.item_type
                    WHEN 'hotels' THEN h.name
                    WHEN 'flights' THEN f.flight_number
                    WHEN 'trains' THEN t.train_number
                 END as item_name,
                 CASE c.item_type
                    WHEN 'hotels' THEN h.price
                    WHEN 'flights' THEN f.price
                    WHEN 'trains' THEN t.price
                 END as item_price
                 FROM cart c
                 LEFT JOIN hotels h ON c.item_id = h.id AND c.item_type = 'hotels'
                 LEFT JOIN flights f ON c.item_id = f.id AND c.item_type = 'flights'
                 LEFT JOIN trains t ON c.item_id = t.id AND c.item_type = 'trains'
                 WHERE c.user_id = ?''', (session['user_id'],))
    cart_items = c.fetchall()
    
    # Calculate total price
    total_price = sum(item[6] * item[4] for item in cart_items if item[6] is not None)
    
    conn.close()
    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

@app.route('/add_to_cart/<item_type>/<int:item_id>')
@login_required
def add_to_cart(item_type, item_id):
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    c.execute('INSERT INTO cart (user_id, item_type, item_id, quantity) VALUES (?, ?, ?, 1)',
             (session['user_id'], item_type, item_id))
    conn.commit()
    conn.close()
    flash('Item added to cart')
    return redirect(url_for('view_cart'))

@app.route('/checkout')
@login_required
def checkout():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    
    try:
        # Move items from cart to bookings
        c.execute('SELECT * FROM cart WHERE user_id = ?', (session['user_id'],))
        cart_items = c.fetchall()
        
        for item in cart_items:
            # Add booking
            c.execute('''INSERT INTO bookings 
                        (user_id, item_type, item_id, quantity, booking_date)
                        VALUES (?, ?, ?, ?, ?)''',
                     (session['user_id'], item[2], item[3], item[4], datetime.now()))
            
            # Update available rooms/seats based on item type
            if item[2] == 'hotels':
                c.execute('UPDATE hotels SET available_rooms = available_rooms - ? WHERE id = ?',
                         (item[4], item[3]))
            elif item[2] in ['flights', 'trains']:
                table = 'flights' if item[2] == 'flights' else 'trains'
                c.execute(f'UPDATE {table} SET available_seats = available_seats - ? WHERE id = ?',
                         (item[4], item[3]))
        
        # Clear cart
        c.execute('DELETE FROM cart WHERE user_id = ?', (session['user_id'],))
        conn.commit()
        flash('Booking confirmed!')
    except sqlite3.Error as e:
        conn.rollback()
        flash('Error processing your booking')
        print(f"Database error: {e}")
        return redirect(url_for('view_cart'))
    finally:
        conn.close()
    
    return redirect(url_for('orders'))

@app.route('/orders')
@login_required
def orders():
    conn = sqlite3.connect('travel.db')
    c = conn.cursor()
    c.execute('''SELECT 
                 b.id,
                 b.user_id,
                 b.item_type,
                 b.item_id,
                 b.quantity,
                 b.booking_date,
                 CASE b.item_type
                    WHEN 'hotels' THEN h.name
                    WHEN 'flights' THEN f.flight_number
                    WHEN 'trains' THEN t.train_number
                 END as item_name,
                 CASE b.item_type
                    WHEN 'hotels' THEN h.location
                    WHEN 'flights' THEN f.origin || ' to ' || f.destination
                    WHEN 'trains' THEN t.origin || ' to ' || t.destination
                 END as location_info,
                 CASE b.item_type
                    WHEN 'hotels' THEN h.price
                    WHEN 'flights' THEN f.price
                    WHEN 'trains' THEN t.price
                 END as price
                 FROM bookings b
                 LEFT JOIN hotels h ON b.item_id = h.id AND b.item_type = 'hotels'
                 LEFT JOIN flights f ON b.item_id = f.id AND b.item_type = 'flights'
                 LEFT JOIN trains t ON b.item_id = t.id AND b.item_type = 'trains'
                 WHERE b.user_id = ?
                 ORDER BY b.booking_date DESC''', (session['user_id'],))
    orders = c.fetchall()
    conn.close()
    return render_template('orders.html', orders=orders)

# Add new routes for flight and train booking
@app.route('/transport/<mode>')
def transport_search(mode):
    if mode not in ['flights', 'trains']:
        return redirect(url_for('home'))
    locations = AIRPORTS if mode == 'flights' else TRAIN_STATIONS
    return render_template('transport_search.html', mode=mode, locations=locations)

@app.route('/transport/<mode>/search')
def transport_results(mode):
    origin = request.args.get('origin')
    destination = request.args.get('destination')
    
    if origin and destination and origin != destination:
        locations = AIRPORTS if mode == 'flights' else TRAIN_STATIONS
        price = calculate_price(locations[origin]['city'], 
                             locations[destination]['city'], 
                             mode)
        
        conn = sqlite3.connect('travel.db')
        c = conn.cursor()
        
        # Check if this route already exists
        table_name = 'flights' if mode == 'flights' else 'trains'
        number_field = 'flight_number' if mode == 'flights' else 'train_number'
        transport_number = f"{'FL' if mode == 'flights' else 'TR'}{origin}{destination}"
        
        c.execute(f'SELECT * FROM {table_name} WHERE {number_field} = ?', (transport_number,))
        existing_transport = c.fetchone()
        
        if existing_transport:
            transport_id = existing_transport[0]
        else:
            if mode == 'flights':
                c.execute('''INSERT INTO flights (flight_number, origin, destination, price, available_seats)
                            VALUES (?, ?, ?, ?, ?)''',
                         (transport_number, locations[origin]['name'], 
                          locations[destination]['name'], price, 60))
            else:
                c.execute('''INSERT INTO trains (train_number, origin, destination, price, available_seats)
                            VALUES (?, ?, ?, ?, ?)''',
                         (transport_number, locations[origin]['name'], 
                          locations[destination]['name'], price, 60))
            transport_id = c.lastrowid
            conn.commit()
        
        conn.close()
        
        result = {
            'id': transport_id,
            'number': transport_number,
            'origin': locations[origin]['name'],
            'destination': locations[destination]['name'],
            'price': price,
            'available_seats': 60
        }
        
        return render_template('transport_results.html',
                             mode=mode,
                             result=result)
    
    flash('Please select valid origin and destination')
    return redirect(url_for('transport_search', mode=mode))

if __name__ == '__main__':
    socketio.run(app, debug=True)
