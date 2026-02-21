# Store/tests/test_html_structure.py
# @ai-rules:
# 1. [Pattern]: Static HTML structure validation -- reads index.html as text, no browser needed.
# 2. [Constraint]: Each check is a separate assertion so pytest reports exactly which element is missing.
# 3. [Gotcha]: Path is relative to this test file's location, not cwd.

from pathlib import Path


def _load_html() -> str:
    html_path = Path(__file__).parent.parent / "src" / "app" / "static" / "index.html"
    assert html_path.exists(), f"File not found: {html_path}"
    return html_path.read_text()


def test_tabs_present():
    content = _load_html()
    assert 'id="viewTabs"' in content, "Tab container #viewTabs not found"
    assert "Catalog" in content, "Catalog tab label not found"
    assert "Inventory" in content, "Inventory tab label not found"


def test_catalog_grid_structure():
    content = _load_html()
    assert 'id="catalog-grid"' in content, "Catalog grid #catalog-grid not found"
    assert "catalog-card" in content, "catalog-card class not found"


def test_description_column_in_table():
    content = _load_html()
    assert "<th>Description</th>" in content, "Description column header not found"


def test_add_product_description_field():
    content = _load_html()
    assert 'id="add-description"' in content, "Add Product description field not found"


def test_edit_product_description_field():
    content = _load_html()
    assert 'id="edit-description"' in content, "Edit Product description field not found"


def test_js_references_description():
    content = _load_html()
    assert "p.description" in content, "JavaScript reference to p.description not found"
