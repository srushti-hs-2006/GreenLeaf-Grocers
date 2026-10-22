import sqlite3
from werkzeug.security import generate_password_hash

DATABASE = "greenleaf.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'cashier'))
        )
    """)

    # Products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL CHECK(price >= 0),
            stock INTEGER NOT NULL DEFAULT 0 CHECK(stock >= 0),
            reorder_level INTEGER NOT NULL DEFAULT 5,
            expiry_date TEXT,
            supplier TEXT
        )
    """)

    # Sales table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT UNIQUE NOT NULL,
            user_id INTEGER,
            sale_date TEXT NOT NULL,
            total_amount REAL NOT NULL CHECK(total_amount >= 0),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Items within each bill
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL CHECK(unit_price >= 0),
            subtotal REAL NOT NULL CHECK(subtotal >= 0),
            FOREIGN KEY(sale_id) REFERENCES sales(id),
            FOREIGN KEY(product_id) REFERENCES products(id)
        )
    """)

    # Create default accounts only if they don't already exist
    users = [
        ("admin", generate_password_hash("Admin@123"), "admin"),
        ("cashier", generate_password_hash("Cashier@123"), "cashier")
    ]

    cursor.executemany("""
        INSERT OR IGNORE INTO users (username, password, role)
        VALUES (?, ?, ?)
    """, users)

    # Sample grocery products
    products = [
        ("Rice", "Grains", 60.00, 100, 10, "2027-12-31", "ABC Suppliers"),
        ("Milk", "Dairy", 30.00, 50, 10, "2026-11-30", "Fresh Dairy"),
        ("Bread", "Bakery", 40.00, 25, 5, "2026-10-28", "Daily Bakery"),
        ("Apples", "Fruits", 120.00, 40, 8, "2026-11-15", "Green Farms"),
        ("Cooking Oil", "Essentials", 150.00, 35, 8, "2027-06-30", "Sun Suppliers"),
        ("Eggs", "Dairy", 7.00, 60, 12, "2026-11-05", "Happy Poultry"),
        ("Sugar", "Essentials", 45.00, 80, 10, "2027-12-31", "ABC Suppliers"),
        ("Tomatoes", "Vegetables", 35.00, 8, 10, "2026-10-25", "Green Farms")
    ]

    cursor.executemany("""
        INSERT INTO products
        (name, category, price, stock, reorder_level, expiry_date, supplier)
        SELECT ?, ?, ?, ?, ?, ?, ?
        WHERE NOT EXISTS (
            SELECT 1 FROM products WHERE name = ?
        )
    """, [
        (*product, product[0]) for product in products
    ])

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("GreenLeaf database initialized successfully!")