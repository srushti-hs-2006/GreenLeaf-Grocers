import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from database import init_db, get_db_connection

# ---------------- PAGE CONFIGURATION ----------------

st.set_page_config(
    page_title="GreenLeaf Grocers",
    page_icon="🥬",
    layout="wide"
)

# Initialize database
init_db()

st.title("🥬 GreenLeaf Grocers")
st.caption("Grocery Store Management System")

# ---------------- DATABASE HELPERS ----------------

def fetch_dataframe(query, params=()):
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(query, conn, params=params)
        return df
    finally:
        conn.close()


def get_products():
    return fetch_dataframe(
        "SELECT * FROM products ORDER BY name"
    )


# ---------------- SIDEBAR ----------------

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Inventory", "Billing", "Sales Reports"]
)

# ---------------- DASHBOARD ----------------

if page == "Dashboard":
    st.header("📊 Dashboard Overview")

    metrics = fetch_dataframe("""
        SELECT
            COUNT(*) AS total_products,
            COALESCE(SUM(stock), 0) AS total_stock,
            COALESCE(SUM(
                CASE WHEN stock <= reorder_level
                THEN 1 ELSE 0 END
            ), 0) AS low_stock
        FROM products
    """)

    sales = fetch_dataframe("""
        SELECT
            COUNT(*) AS total_bills,
            COALESCE(SUM(total_amount), 0) AS revenue
        FROM sales
    """)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Products",
        int(metrics.iloc[0]["total_products"])
    )

    col2.metric(
        "Units in Stock",
        int(metrics.iloc[0]["total_stock"])
    )

    col3.metric(
        "Low-Stock Products",
        int(metrics.iloc[0]["low_stock"])
    )

    col4.metric(
        "Total Revenue",
        f"₹{sales.iloc[0]['revenue']:,.2f}"
    )

    st.subheader("📦 Inventory Summary")

    products = get_products()

    if not products.empty:
        st.dataframe(products, use_container_width=True)

        st.subheader("📉 Stock Levels")

        chart_data = products.set_index("name")["stock"]
        st.bar_chart(chart_data)

        low_stock = products[
            products["stock"] <= products["reorder_level"]
        ]

        if not low_stock.empty:
            st.warning("Some products have low stock!")
            st.dataframe(
                low_stock[["name", "stock", "reorder_level"]],
                use_container_width=True
            )

        if "expiry_date" in products.columns:
            st.subheader("⏰ Expiry Alerts")

            products["expiry_date"] = pd.to_datetime(
                products["expiry_date"],
                errors="coerce"
            )

            today = pd.Timestamp.today().normalize()

            expired = products[
                products["expiry_date"].notna()
                & (products["expiry_date"] < today)
            ]

            expiring = products[
                products["expiry_date"].notna()
                & (products["expiry_date"] >= today)
                & (
                    products["expiry_date"]
                    <= today + pd.Timedelta(days=30)
                )
            ]

            if not expired.empty:
                st.error("Expired products")
                st.dataframe(
                    expired[["name", "expiry_date"]],
                    use_container_width=True
                )

            if not expiring.empty:
                st.warning("Products expiring within 30 days")
                st.dataframe(
                    expiring[["name", "expiry_date"]],
                    use_container_width=True
                )

    st.subheader("💰 Recent Sales")

    recent_sales = fetch_dataframe("""
        SELECT bill_number, sale_date, total_amount
        FROM sales
        ORDER BY id DESC
        LIMIT 10
    """)

    if recent_sales.empty:
        st.info("No sales recorded yet.")
    else:
        st.dataframe(recent_sales, use_container_width=True)


# ---------------- INVENTORY ----------------

elif page == "Inventory":
    st.header("📦 Inventory Management")

    products = get_products()

    if not products.empty:
        st.dataframe(products, use_container_width=True)

    st.subheader("➕ Add a Product")

    with st.form("add_product_form"):
        name = st.text_input("Product Name")
        category = st.text_input("Category")
        price = st.number_input("Price (₹)", min_value=0.0, step=1.0)
        stock = st.number_input("Stock Quantity", min_value=0, step=1)
        reorder = st.number_input(
            "Reorder Level", min_value=0, value=5, step=1
        )
        expiry = st.date_input("Expiry Date")
        supplier = st.text_input("Supplier")

        submitted = st.form_submit_button("Add Product")

        if submitted:
            if not name.strip() or not category.strip():
                st.error("Product name and category are required.")
            else:
                conn = get_db_connection()

                try:
                    conn.execute("""
                        INSERT INTO products
                        (name, category, price, stock,
                         reorder_level, expiry_date, supplier)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        name.strip(),
                        category.strip(),
                        price,
                        stock,
                        reorder,
                        expiry.isoformat(),
                        supplier.strip()
                    ))

                    conn.commit()
                    st.success("Product added successfully!")
                    st.rerun()

                except sqlite3.IntegrityError:
                    st.error("Could not add this product.")

                finally:
                    conn.close()

    st.subheader("✏️ Update Product Stock")

    if not products.empty:
        product_options = {
            f"{row['name']} (ID: {row['id']})": int(row["id"])
            for _, row in products.iterrows()
        }

        selected = st.selectbox(
            "Select Product",
            list(product_options.keys()),
            key="stock_product"
        )

        product_id = product_options[selected]

        current_product = products[
            products["id"] == product_id
        ].iloc[0]

        new_stock = st.number_input(
            "New Stock Quantity",
            min_value=0,
            value=int(current_product["stock"]),
            step=1
        )

        if st.button("Update Stock"):
            conn = get_db_connection()

            try:
                conn.execute(
                    "UPDATE products SET stock = ? WHERE id = ?",
                    (new_stock, product_id)
                )
                conn.commit()
                st.success("Stock updated!")
                st.rerun()
            finally:
                conn.close()


# ---------------- BILLING ----------------

elif page == "Billing":
    st.header("🧾 Create a Bill")

    products = get_products()

    if products.empty:
        st.warning("Add products before creating a bill.")

    else:
        available = products[products["stock"] > 0]

        if available.empty:
            st.warning("No products are currently in stock.")

        else:
            options = {
                f"{row['name']} — ₹{row['price']:.2f} "
                f"(Stock: {row['stock']})": int(row["id"])
                for _, row in available.iterrows()
            }

            with st.form("billing_form"):
                selected = st.selectbox(
                    "Choose Product",
                    list(options.keys())
                )

                product_id = options[selected]

                product = available[
                    available["id"] == product_id
                ].iloc[0]

                quantity = st.number_input(
                    "Quantity",
                    min_value=1,
                    max_value=int(product["stock"]),
                    value=1,
                    step=1
                )

                total = float(product["price"]) * quantity

                st.metric("Bill Total", f"₹{total:,.2f}")

                submit_bill = st.form_submit_button("Complete Sale")

                if submit_bill:
                    conn = get_db_connection()

                    try:
                        conn.execute("BEGIN IMMEDIATE")

                        current = conn.execute(
                            "SELECT stock, price FROM products WHERE id = ?",
                            (product_id,)
                        ).fetchone()

                        if current is None or current["stock"] < quantity:
                            raise ValueError(
                                "Insufficient stock. Refresh and try again."
                            )

                        actual_total = float(current["price"]) * quantity

                        bill_number = (
                            "GL-"
                            + datetime.now().strftime("%Y%m%d%H%M%S%f")
                        )

                        cursor = conn.execute("""
                            INSERT INTO sales
                            (bill_number, user_id, sale_date, total_amount)
                            VALUES (?, NULL, ?, ?)
                        """, (
                            bill_number,
                            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            actual_total
                        ))

                        sale_id = cursor.lastrowid

                        conn.execute("""
                            INSERT INTO sale_items
                            (sale_id, product_id, quantity,
                             unit_price, subtotal)
                            VALUES (?, ?, ?, ?, ?)
                        """, (
                            sale_id,
                            product_id,
                            quantity,
                            current["price"],
                            actual_total
                        ))

                        conn.execute(
                            "UPDATE products SET stock = stock - ? WHERE id = ?",
                            (quantity, product_id)
                        )

                        conn.commit()

                        st.success("Sale completed successfully!")
                        st.write(f"**Bill Number:** {bill_number}")
                        st.write(f"**Product:** {product['name']}")
                        st.write(f"**Quantity:** {quantity}")
                        st.write(f"**Total:** ₹{actual_total:,.2f}")

                    except (sqlite3.Error, ValueError) as error:
                        conn.rollback()
                        st.error(f"Sale could not be completed: {error}")

                    finally:
                        conn.close()


# ---------------- SALES REPORTS ----------------

elif page == "Sales Reports":
    st.header("📈 Sales Reports")

    sales = fetch_dataframe("""
        SELECT bill_number, sale_date, total_amount
        FROM sales
        ORDER BY sale_date DESC
    """)

    if sales.empty:
        st.info("No sales reports available yet.")

    else:
        sales["sale_date"] = pd.to_datetime(
            sales["sale_date"],
            errors="coerce"
        )

        col1, col2 = st.columns(2)

        with col1:
            start_date = st.date_input(
                "Start Date",
                value=sales["sale_date"].min().date()
            )

        with col2:
            end_date = st.date_input(
                "End Date",
                value=sales["sale_date"].max().date()
            )

        if start_date > end_date:
            st.error("Start date must be before or equal to end date.")

        else:
            filtered = sales[
                sales["sale_date"].dt.date.between(
                    start_date, end_date
                )
            ]

            st.metric(
                "Revenue in Selected Period",
                f"₹{filtered['total_amount'].sum():,.2f}"
            )

            st.dataframe(filtered, use_container_width=True)

            csv_data = filtered.to_csv(index=False).encode("utf-8")

            st.download_button(
                "⬇️ Download Sales Report (CSV)",
                data=csv_data,
                file_name="greenleaf_sales_report.csv",
                mime="text/csv"
            )

            if not filtered.empty:
                daily = (
                    filtered.assign(
                        date=filtered["sale_date"].dt.date
                    )
                    .groupby("date")["total_amount"]
                    .sum()
                )

                st.subheader("Daily Revenue")
                st.line_chart(daily)