# Store/tests/test_html_structure.py
# @ai-rules:
# 1. [Pattern]: Static HTML structure validation -- reads index.html and admin.html as text, no browser needed.
# 2. [Constraint]: Each check is a separate assertion so pytest reports exactly which element is missing.
# 3. [Gotcha]: Path is relative to this test file's location, not cwd.

from pathlib import Path


def _load_html(filename="index.html") -> str:
    html_path = Path(__file__).parent.parent / "src" / "app" / "static" / filename
    assert html_path.exists(), f"File not found: {html_path}"
    return html_path.read_text()


# ---- Storefront (index.html) tests ----

def test_tabs_present():
    content = _load_html()
    assert 'id="viewTabs"' in content, "Tab container #viewTabs not found"
    assert "Catalog" in content, "Catalog tab label not found"
    assert "Cart" in content, "Cart tab label not found"
    assert "My Orders" in content, "My Orders tab label not found"


def test_storefront_no_admin_tabs():
    content = _load_html()
    # These admin-only tabs should NOT appear in storefront
    assert 'id="inventory-tab"' not in content, "Inventory tab should not be in storefront"
    assert 'id="dashboard-tab"' not in content, "Dashboard tab should not be in storefront"
    assert 'id="suppliers-tab"' not in content, "Suppliers tab should not be in storefront"
    assert 'id="customers-tab"' not in content, "Customers tab should not be in storefront"
    assert 'id="alerts-tab"' not in content, "Alerts tab should not be in storefront"
    assert 'id="coupons-tab"' not in content, "Coupons tab should not be in storefront"
    assert 'id="invoices-tab"' not in content, "Invoices tab should not be in storefront"


def test_catalog_grid_structure():
    content = _load_html()
    assert 'id="catalog-grid"' in content, "Catalog grid #catalog-grid not found"
    assert "catalog-card" in content, "catalog-card class not found"


def test_order_detail_toggle_function():
    content = _load_html()
    assert 'toggleOrderDetail' in content, "toggleOrderDetail function not found"


def test_order_detail_css_classes():
    content = _load_html()
    assert 'order-detail-row' in content, "order-detail-row CSS class not found"
    assert 'order-row' in content, "order-row CSS class not found"


def test_storefront_uses_shared_css():
    content = _load_html()
    assert '/static/shared.css' in content, "Storefront should reference shared.css"


# ---- Admin (admin.html) tests ----

def test_admin_tabs_present():
    content = _load_html("admin.html")
    assert 'id="viewTabs"' in content, "Tab container #viewTabs not found in admin"
    assert 'id="dashboard-tab"' in content, "Dashboard tab not found in admin"
    assert 'id="inventory-tab"' in content, "Inventory tab not found in admin"
    assert 'id="orders-tab"' in content, "Orders tab not found in admin"
    assert 'id="customers-tab"' in content, "Customers tab not found in admin"
    assert 'id="suppliers-tab"' in content, "Suppliers tab not found in admin"
    assert 'id="alerts-tab"' in content, "Alerts tab not found in admin"
    assert 'id="coupons-tab"' in content, "Coupons tab not found in admin"
    assert 'id="invoices-tab"' in content, "Invoices tab not found in admin"


def test_admin_description_column_in_table():
    content = _load_html("admin.html")
    assert "<th>Description</th>" in content, "Description column header not found in admin"


def test_admin_add_product_description_field():
    content = _load_html("admin.html")
    assert 'id="add-description"' in content, "Add Product description field not found in admin"


def test_admin_edit_product_description_field():
    content = _load_html("admin.html")
    assert 'id="edit-description"' in content, "Edit Product description field not found in admin"


def test_admin_js_references_description():
    content = _load_html("admin.html")
    assert "p.description" in content, "JavaScript reference to p.description not found in admin"


def test_admin_uses_shared_css():
    content = _load_html("admin.html")
    assert '/static/shared.css' in content, "Admin should reference shared.css"


def test_admin_no_catalog_tab():
    content = _load_html("admin.html")
    assert 'id="catalog-tab"' not in content, "Catalog tab should not be in admin"


def test_admin_no_cart_tab():
    content = _load_html("admin.html")
    assert 'id="cart-tab"' not in content, "Cart tab should not be in admin"
