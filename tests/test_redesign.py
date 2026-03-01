import sys
import os
import unittest
from unittest.mock import MagicMock
import asyncio

# Add src to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from app.models import ProductCreate, ProductUpdate
from app.routes import products as products_routes

class TestStoreRedesign(unittest.TestCase):
    def setUp(self):
        self.mock_pool = MagicMock()
        self.mock_conn = MagicMock()
        self.mock_cursor = MagicMock()
        
        self.mock_pool.getconn.return_value = self.mock_conn
        self.mock_conn.cursor.return_value.__enter__.return_value = self.mock_cursor
        
        self.mock_request = MagicMock()
        self.mock_request.app.state.db_pool = self.mock_pool

    def test_list_products_sql(self):
        """Verify list_products selects description and returns paginated envelope."""
        # Pagination requires fetchone for COUNT(*) first
        self.mock_cursor.fetchone.return_value = (1,)
        # fetchall returns rows (9 columns: id, name, price, stock, sku, image_data, description, supplier_id, reorder_threshold)
        self.mock_cursor.fetchall.return_value = [
            ('id1', 'name1', 10.0, 5, 'sku1', 'img1', 'desc1', None, 10)
        ]

        # Must pass explicit ints -- Query(...) objects are FastAPI DI and don't resolve in direct calls
        result = asyncio.run(products_routes.list_products(self.mock_request, page=1, limit=20))

        # Verify the SELECT call includes description (check second execute call)
        select_calls = [
            call for call in self.mock_cursor.execute.call_args_list
            if "SELECT id" in call[0][0]
        ]
        self.assertEqual(len(select_calls), 1)
        self.assertIn("description", select_calls[0][0][0])
        # Result is now a PaginatedResponse -- check items
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].description, 'desc1')

    def test_create_product_sql(self):
        """Verify create_product inserts description."""
        product_in = ProductCreate(name="n", price=1, stock=1, sku="s", description="d")
        
        asyncio.run(products_routes.create_product(product_in, self.mock_request))
        
        call_args = self.mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        self.assertIn("INSERT INTO products", sql)
        self.assertIn("description", sql)
        # Check params contains 'd'
        self.assertIn("d", params)

    def test_update_product_sql(self):
        """Verify update_product updates description."""
        product_in = ProductCreate(name="n", price=1, stock=1, sku="s", description="new_d")
        self.mock_cursor.fetchone.return_value = ('id1', 'n', 1.0, 1, 's', 'img', 'new_d', None, 10)

        asyncio.run(products_routes.update_product("id1", product_in, self.mock_request))
        
        call_args = self.mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        
        self.assertIn("UPDATE products", sql)
        self.assertIn("description = %s", sql)
        self.assertIn("new_d", params)

if __name__ == '__main__':
    unittest.main()
