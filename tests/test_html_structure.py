import re
from pathlib import Path

def test_html_structure():
    html_path = Path(__file__).parent.parent / "src" / "app" / "static" / "index.html"
    
    if not html_path.exists():
        print(f"FAILURE: File not found: {html_path}")
        return

    content = html_path.read_text()

    # Check for Tabs
    if 'id="viewTabs"' in content and 'Catalog' in content and 'Inventory' in content:
        print("SUCCESS: Tabs found.")
    else:
        print("FAILURE: Tabs not found.")

    # Check for Catalog grid
    if 'id="catalog-grid"' in content and 'catalog-card' in content:
        print("SUCCESS: Catalog grid structure found.")
    else:
        print("FAILURE: Catalog grid structure not found.")

    # Check for Description column in table
    if '<th>Description</th>' in content:
        print("SUCCESS: Description column header found.")
    else:
        print("FAILURE: Description column header not found.")

    # Check for Description field in Add form
    if 'id="add-description"' in content:
        print("SUCCESS: Add Product description field found.")
    else:
        print("FAILURE: Add Product description field not found.")

    # Check for Description field in Edit form
    if 'id="edit-description"' in content:
        print("SUCCESS: Edit Product description field found.")
    else:
        print("FAILURE: Edit Product description field not found.")

    # Check JS logic for rendering description
    if 'p.description' in content:
        print("SUCCESS: JavaScript reference to p.description found.")
    else:
        print("FAILURE: JavaScript reference to p.description not found.")

if __name__ == "__main__":
    test_html_structure()
