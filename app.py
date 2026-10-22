from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import check_password_hash
from functools import wraps
from datetime import datetime, date
from database import get_db_connection, init_db
import sqlite3
import csv
import io

app = Flask(__name__)
app.secret_key = "change-this-before-deployment"


# ---------- LOGIN PROTECTION ----------

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if session.get("role") not in roles:
                flash("You do not have permission to access this page.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


# ---------- LOGIN ----------

@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
            

        if user and check_password_hash(user["password"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- DASHBOARD ----------

@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_db_connection()

    revenue = conn.execute(
        "SELECT COALESCE(SUM(total_amount), 0) FROM sales"
    ).fetchone()[0]

    bill_count = conn.execute(
        "SELECT COUNT(*) FROM sales"
    ).fetchone()[0]

    average_bill = revenue / bill_count if bill_count else 0

    low_stock = conn.execute(
        "SELECT COUNT(*) FROM products WHERE stock <= reorder_level"
    ).fetchone()[0]

    products = conn.execute(
        "SELECT * FROM products ORDER BY name"
    ).fetchall()

    top_products = conn.execute("""
        SELECT p.name, SUM(si.quantity) AS units_sold,
               SUM(si.subtotal) AS revenue
        FROM sale_items si
        JOIN products p ON p.id = si.product_id
        GROUP BY p.id, p.name
        ORDER BY units_sold DESC
        LIMIT 5
    """).fetchall()

    daily_sales = conn.execute("""
        SELECT DATE(sale_date) AS day, SUM(total_amount) AS revenue
        FROM sales
        WHERE DATE(sale_date) >= DATE('now', '-6 days')
        GROUP BY DATE(sale_date)
        ORDER BY day
    """).fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        revenue=revenue,
        bill_count=bill_count,
        average_bill=average_bill,
        low_stock=low_stock,
        products=products,
        top_products=top_products,
        daily_sales=daily_sales
    )


# ---------- PRODUCT MANAGEMENT ----------

@app.route("/products", methods=["GET", "POST"])
@login_required
@role_required("admin")
def products():
    conn = get_db_connection()

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            price = float(request.form.get("price", ""))
            stock = int(request.form.get("stock", ""))
            reorder_level = int(request.form.get("reorder_level", 5))
            expiry_date = request.form.get("expiry_date") or None
            supplier = request.form.get("supplier", "").strip()

            if not name or not category:
                raise ValueError("Name and category are required.")

            if price < 0 or stock < 0 or reorder_level < 0:
                raise ValueError("Values cannot be negative.")

            conn.execute("""
                INSERT INTO products
                (name, category, price, stock, reorder_level, expiry_date, supplier)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                name, category, price, stock, reorder_level,
                expiry_date, supplier
            ))

            conn.commit()
            flash("Product added successfully!", "success")

        except (ValueError, sqlite3.IntegrityError):
            flash("Please enter valid product details.", "error")

        finally:
            conn.close()

        return redirect(url_for("products"))

    search = request.args.get("search", "").strip()

    product_list = conn.execute("""
        SELECT * FROM products
        WHERE name LIKE ? OR category LIKE ?
        ORDER BY name
    """, (f"%{search}%", f"%{search}%")).fetchall()

    conn.close()

    return render_template(
        "products.html",
        products=product_list,
        search=search
    )


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin")
def edit_product(product_id):
    conn = get_db_connection()

    product = conn.execute(
        "SELECT * FROM products WHERE id = ?", (product_id,)
    ).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            price = float(request.form.get("price", ""))
            stock = int(request.form.get("stock", ""))
            reorder_level = int(request.form.get("reorder_level", 5))
            expiry_date = request.form.get("expiry_date") or None
            supplier = request.form.get("supplier", "").strip()

            if not name or not category:
                raise ValueError()

            if price < 0 or stock < 0 or reorder_level < 0:
                raise ValueError()

            conn.execute("""
                UPDATE products
                SET name=?, category=?, price=?, stock=?,
                    reorder_level=?, expiry_date=?, supplier=?
                WHERE id=?
            """, (
                name, category, price, stock, reorder_level,
                expiry_date, supplier, product_id
            ))

            conn.commit()
            flash("Product updated successfully!", "success")
            conn.close()
            return redirect(url_for("products"))

        except (ValueError, sqlite3.IntegrityError):
            flash("Please enter valid product details.", "error")

    conn.close()
    return render_template("products.html", edit_product=product)


@app.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def delete_product(product_id):
    conn = get_db_connection()

    product = conn.execute(
        "SELECT id FROM products WHERE id = ?", (product_id,)
    ).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    sold = conn.execute(
        "SELECT COUNT(*) FROM sale_items WHERE product_id = ?",
        (product_id,)
    ).fetchone()[0]

    if sold:
        conn.close()
        flash("Products in previous bills cannot be deleted.", "error")
        return redirect(url_for("products"))

    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

    flash("Product deleted successfully.", "success")
    return redirect(url_for("products"))


# ---------- BILLING ----------

@app.route("/billing", methods=["GET", "POST"])
@login_required
def billing():
    conn = get_db_connection()

    available_products = conn.execute("""
        SELECT * FROM products WHERE stock > 0 ORDER BY name
    """).fetchall()

    if request.method == "POST":
        items = request.form.getlist("product_id")
        quantities = request.form.getlist("quantity")

        if not items or len(items) != len(quantities):
            conn.close()
            flash("Please add products to the bill.", "error")
            return redirect(url_for("billing"))

        try:
            cart = {}

            for product_id, quantity in zip(items, quantities):
                pid = int(product_id)
                qty = int(quantity)

                if qty <= 0:
                    raise ValueError()

                cart[pid] = cart.get(pid, 0) + qty

            conn.execute("BEGIN IMMEDIATE")

            total = 0
            bill_items = []

            for pid, qty in cart.items():
                product = conn.execute(
                    "SELECT * FROM products WHERE id = ?", (pid,)
                ).fetchone()

                if not product or product["stock"] < qty:
                    raise ValueError(
                        "A product is unavailable or has insufficient stock."
                    )

                subtotal = round(product["price"] * qty, 2)
                total += subtotal

                bill_items.append(
                    (pid, qty, product["price"], subtotal)
                )

            bill_number = "GL-" + datetime.now().strftime("%Y%m%d%H%M%S%f")
            sale_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cursor = conn.execute("""
                INSERT INTO sales
                (bill_number, user_id, sale_date, total_amount)
                VALUES (?, ?, ?, ?)
            """, (
                bill_number,
                session["user_id"],
                sale_date,
                round(total, 2)
            ))

            sale_id = cursor.lastrowid

            for pid, qty, price, subtotal in bill_items:
                conn.execute("""
                    INSERT INTO sale_items
                    (sale_id, product_id, quantity, unit_price, subtotal)
                    VALUES (?, ?, ?, ?, ?)
                """, (sale_id, pid, qty, price, subtotal))

                updated = conn.execute("""
                    UPDATE products SET stock = stock - ?
                    WHERE id = ? AND stock >= ?
                """, (qty, pid, qty))

                if updated.rowcount != 1:
                    raise ValueError("Stock changed; please try again.")

            conn.commit()
            conn.close()

            return render_template(
                "billing.html",
                products=[],
                bill={
                    "number": bill_number,
                    "date": sale_date,
                    "total": round(total, 2),
                    "items": [
                        {
                            "name": get_product_name(pid),
                            "quantity": qty,
                            "price": price,
                            "subtotal": subtotal
                        }
                        for pid, qty, price, subtotal in bill_items
                    ]
                }
            )

        except (ValueError, sqlite3.IntegrityError) as error:
            conn.rollback()
            flash(str(error) or "Invalid bill details.", "error")

        finally:
            conn.close()

        return redirect(url_for("billing"))

    conn.close()
    return render_template("billing.html", products=available_products)


def get_product_name(product_id):
    conn = get_db_connection()
    row = conn.execute(
        "SELECT name FROM products WHERE id = ?", (product_id,)
    ).fetchone()
    conn.close()
    return row["name"] if row else "Unknown product"


# ---------- CSV EXPORT ----------

@app.route("/reports/export")
@login_required
@role_required("admin")
def export_report():
    conn = get_db_connection()

    sales = conn.execute("""
        SELECT bill_number, sale_date, total_amount
        FROM sales ORDER BY sale_date DESC
    """).fetchall()

    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Bill Number", "Sale Date", "Total Amount"])

    for sale in sales:
        writer.writerow([
            sale["bill_number"],
            sale["sale_date"],
            sale["total_amount"]
        ])

    from flask import Response

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={
            "Content-Disposition":
                "attachment; filename=greenleaf_sales_report.csv"
        }
    )


# ---------- START APPLICATION ----------

if __name__ == "__main__":
    init_db()
    app.run(debug=True)