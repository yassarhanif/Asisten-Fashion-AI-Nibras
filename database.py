import os
import json
import sqlite3
import glob

class ProductDatabase:
    def __init__(self, products_dir="Products"):
        self.products_dir = products_dir
        self.conn = sqlite3.connect(':memory:', check_same_thread=False)
        
        # Register REGEXP function for word-boundary matching
        import re
        def _regexp(expr, item):
            if item is None: return False
            return re.search(expr, str(item), re.IGNORECASE) is not None
        self.conn.create_function("REGEXP", 2, _regexp)
        
        self.cursor = self.conn.cursor()
        self._create_table()
        self._load_data()

    def _create_table(self):
        self.cursor.execute('''
            CREATE TABLE products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product_id TEXT,
                name_product TEXT COLLATE NOCASE,
                brand TEXT COLLATE NOCASE,
                category TEXT COLLATE NOCASE,
                description TEXT COLLATE NOCASE,
                thumbnail TEXT,
                sku TEXT COLLATE NOCASE,
                size TEXT COLLATE NOCASE,
                color TEXT COLLATE NOCASE,
                price INTEGER,
                stock INTEGER,
                is_new BOOLEAN,
                discount INTEGER,
                weight INTEGER,
                created_at TEXT
            )
        ''')
        self.cursor.execute('CREATE INDEX idx_name ON products (name_product)')
        self.cursor.execute('CREATE INDEX idx_color ON products (color)')
        self.cursor.execute('CREATE INDEX idx_price ON products (price)')
        self.cursor.execute('CREATE INDEX idx_stock ON products (stock)')
        self.cursor.execute('CREATE INDEX idx_is_new ON products (is_new)')
        self.cursor.execute('CREATE INDEX idx_discount ON products (discount)')
        self.conn.commit()

    def _load_data(self):
        json_files = glob.glob(os.path.join(self.products_dir, "*.json"))
        products_to_insert = []

        for file_path in json_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    product_id = data.get('product_id', '')
                    name_product = data.get('name_product', '')
                    brand = data.get('brand', {}).get('name_brand', '')
                    category = data.get('category3', '')
                    description = data.get('description', '')
                    product_thumbnail = data.get('thumbnails', [None])[0] if data.get('thumbnails') else None
                    is_new = data.get('new_product', False)
                    discount = data.get('diskon_product', 0)
                    created_at = data.get('created_at', '')
                    
                    variants = data.get('variants', [])
                    for v in variants:
                        variant_thumbnail = v.get('thumbnails')
                        if not variant_thumbnail or variant_thumbnail == '""':
                            variant_thumbnail = product_thumbnail

                        products_to_insert.append((
                            product_id,
                            name_product,
                            brand,
                            category,
                            description,
                            variant_thumbnail,
                            v.get('sku', ''),
                            v.get('variant1_size', ''),
                            v.get('variant2_color', ''),
                            v.get('price_tags', 0),
                            v.get('stock', 0),
                            1 if is_new else 0,
                            discount,
                            v.get('package_weight', 0),
                            created_at
                        ))
            except Exception as e:
                print(f"Error loading {file_path}: {e}")

        self.cursor.executemany('''
            INSERT INTO products (
                product_id, name_product, brand, category, description, 
                thumbnail, sku, size, color, price, stock,
                is_new, discount, weight, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', products_to_insert)
        self.conn.commit()
        print(f"Loaded {len(products_to_insert)} variants from {len(json_files)} products.")

    def search_products(self, keyword=None, color=None, max_price=None, min_price=None, in_stock=True, only_new=False, only_discounted=False, size=None, feature=None, brand=None, category=None, sku=None, limit=40, sort_by="newest"):
        original_color = color
        
        results = self._execute_search(keyword=keyword, color=color, max_price=max_price, min_price=min_price,
            in_stock=in_stock, only_new=only_new, only_discounted=only_discounted,
            size=size, feature=feature, brand=brand, category=category, sku=sku,
            limit=limit, sort_by=sort_by)
        
        if not results and color:
            fuzzy_color = self._resolve_color(color)
            if fuzzy_color and fuzzy_color != original_color:
                results = self._execute_search(keyword=keyword, color=fuzzy_color, max_price=max_price, min_price=min_price,
                    in_stock=in_stock, only_new=only_new, only_discounted=only_discounted,
                    size=size, feature=feature, brand=brand, category=category, sku=sku,
                    limit=limit, sort_by=sort_by)
        
        return results
    
    def _execute_search(self, keyword=None, color=None, max_price=None, min_price=None, in_stock=True, only_new=False, only_discounted=False, size=None, feature=None, brand=None, category=None, sku=None, limit=40, sort_by="newest"):
        """Internal search execution."""
        query = """
            SELECT product_id, name_product, brand, category, size, color, 
                   price, stock, thumbnail, sku, description, is_new, discount, weight 
            FROM products WHERE 1=1
        """
        params = []

        if keyword:
            words = keyword.split()
            product_types = ['GAMIS', 'KOKO', 'TUNIK', 'MUKENA', 'SARIMBIT', 'HIJAB', 'SCARF', 'SKIRT', 'PANTS', 'KULOT', 'ATASAN', 'DRESS', 'OUTER', 'CELANA', 'ROK']
            
            for w in words:
                w_upper = w.upper()
                if w_upper in product_types:
                    # For product types, only search name, brand, category and color to avoid description false positives
                    query += " AND (name_product REGEXP ? OR brand REGEXP ? OR category REGEXP ? OR color REGEXP ?)"
                    params.extend([rf"\b{w}\b", rf"\b{w}\b", rf"\b{w}\b", rf"\b{w}\b"])
                else:
                    # For other words (features like 'panjang', 'busui', 'cotton'), also search the description
                    query += " AND (name_product REGEXP ? OR brand REGEXP ? OR category REGEXP ? OR color REGEXP ? OR COALESCE(description, '') REGEXP ?)"
                    params.extend([rf"\b{w}\b", rf"\b{w}\b", rf"\b{w}\b", rf"\b{w}\b", rf"\b{w}\b"])
            
            # Automatically exclude kids products if the query doesn't ask for them
            k_upper = keyword.upper()
            if 'ANAK' not in k_upper and 'KIDS' not in k_upper and 'REMAJA' not in k_upper:
                query += " AND name_product NOT REGEXP ? AND category NOT REGEXP ?"
                params.extend([r"\b(ANAK|KIDS|REMAJA)\b", r"\b(ANAK|KIDS|REMAJA)\b"])

        if feature:
            query += " AND description LIKE ?"
            params.append(f"%{feature}%")
        
        if color:
            color_upper = color.upper()
            color_groups = [
                ['RED', 'MAROON', 'BURGUNDY', 'MERAH', 'BRICK', 'MAHOGANY', 'CABERNET', 'CHILLI'],
                ['BLUE', 'NAVY', 'DENIM', 'INDIGO', 'BIRU', 'AQUA', 'TEAL', 'TURQUOISE', 'CYAN'],
                ['GREEN', 'ARMY', 'OLIVE', 'MINT', 'SAGE', 'HIJAU', 'EMERALD', 'FOREST', 'MATCHA', 'JADE'],
                ['PURPLE', 'LILAC', 'LAVENDER', 'UNGU', 'TARO', 'PLUM', 'ORCHID', 'VIOLET', 'MAUVE', 'GRAPE'],
                ['BROWN', 'COKLAT', 'CHOCO', 'MOCCA', 'MILO', 'COFFEE', 'CARAMEL', 'LATTE', 'HAZELNUT', 'CINNAMON', 'WOOD'],
                ['GREY', 'GRAY', 'ABU', 'SILVER', 'ASH', 'SMOKE', 'IRON'],
                ['YELLOW', 'KUNING', 'MUSTARD', 'LEMON', 'GOLD'],
                ['WHITE', 'PUTIH', 'IVORY', 'CREAM', 'BROKEN WHITE', 'BONE', 'VANILLA'],
                ['PINK', 'ROSE', 'BLUSH', 'SALEM', 'PEACH', 'CORAL', 'FANTA', 'MAGENTA'],
                ['ORANGE', 'TERRACOTTA', 'CANTALOUPE', 'RUST'],
                ['BLACK', 'HITAM', 'ASWAD', 'CAVIAR', 'JETBLACK', 'JET BLACK']
            ]
            
            target_group = [color_upper]
            for group in color_groups:
                if color_upper in group:
                    target_group = group
                    break
            
            clauses = ["UPPER(color) LIKE ?" for _ in target_group]
            for s in target_group:
                params.append(f"%{s}%")
            query += f" AND ({' OR '.join(clauses)})"

        if size:
            query += " AND size = ?"
            params.append(size)

        if brand:
            query += " AND brand LIKE ?"
            params.append(f"%{brand}%")

        if category:
            query += " AND category LIKE ?"
            params.append(f"%{category}%")

        if sku:
            query += " AND sku LIKE ?"
            params.append(f"%{sku}%")
        
        if max_price:
            query += " AND price <= ?"
            params.append(max_price)

        if min_price:
            query += " AND price >= ?"
            params.append(min_price)
        
        if in_stock:
            query += " AND stock > 0"

        if only_new:
            query += " AND is_new = 1"
        
        if only_discounted:
            query += " AND discount > 0"

        sort_map = {
            "newest": "created_at DESC",
            "price_low": "price ASC",
            "price_high": "price DESC",
            "name": "name_product ASC",
            "stock": "stock DESC",
        }
        order_clause = sort_map.get(sort_by, "created_at DESC")
        query += f" ORDER BY {order_clause} LIMIT ?"
        params.append(limit)
        
        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()
        
        results = []
        for row in rows:
            results.append({
                "product_id": row[0],
                "name_product": row[1],
                "brand": row[2],
                "category": row[3],
                "size": row[4],
                "color": row[5],
                "price": row[6],
                "stock": row[7],
                "thumbnail": row[8],
                "sku": row[9],
                "description": row[10],
                "is_new": bool(row[11]),
                "discount_percent": row[12],
                "weight_grams": row[13]
            })
        
        return results
    
    def _resolve_color(self, color_query):
        """Resolve a color query to best matching known color. Returns None if no match."""
        if not color_query:
            return None
        
        self.cursor.execute("SELECT DISTINCT color FROM products WHERE color != ''")
        known = [row[0].upper() for row in self.cursor.fetchall()]
        
        q = color_query.upper().strip()
        
        if q in known:
            return q
        
        for k in known:
            if q in k and q != k:
                return k
        
        return None

    def _predict_basic_color(self, color):
        """Map extended colors to basic colors. Returns the predicted basic color."""
        if not color:
            return None
        
        q = color.upper().strip()
        
        # Check if it's already a basic color - skip prediction
        basic_colors = {
            'BLACK', 'WHITE', 'BLUE', 'GREEN', 'PURPLE', 'PINK',
            'YELLOW', 'ORANGE', 'BROWN', 'GREY', 'CREAM', 'NAVY', 'BURGUNDY',
            'GOLD', 'SILVER', 'BEIGE', 'CORAL', 'LILAC', 'PEACH', 'OLIVE',
            'TAN', 'MAROON', 'TEAL', 'TURQUOISE', 'LAVENDER', 'MAUVE', 'CORNFLOWER',
            'INDIGO', 'CHOCOLATE', 'COFFEE', 'KHAKI', 'CHARCOAL', 'IVORY',
            'BRONZE', 'COPPER', 'MINT', 'LIME', 'PLUM', 'RUST', 'TANGERINE',
            'AMBER', 'SIENNA', 'WHEAT', 'ECRU', 'FUSHIA', 'MAGENTA', 'AQUA', 'SKY'
        }
        
        if q in basic_colors:
            return None
        
        color_mappings = {
            'HITAM': 'BLACK', 'ASWAD': 'BLACK', 'CAVIAR': 'BLACK', 'ASPHALT': 'CHARCOAL',
            'PUTIH': 'WHITE', 'BROKEN WHITE': 'WHITE', 'BONE WHITE': 'WHITE', 'IVORY': 'CREAM', 'ECRU': 'CREAM',
            'BIRU': 'BLUE', 'BIRU ELEKTRIK': 'BLUE', 'NAVY': 'NAVY', 'DENIM': 'BLUE',
            'BLUE INDIGO': 'INDIGO', 'COBALT BLUE': 'BLUE', 'DEEP BLUE': 'BLUE', 'SKY BLUE': 'SKY',
            'DUSTY BLUE': 'BLUE', 'AZURE': 'BLUE', 'ROYAL BLUE': 'BLUE',
            'HIJAU': 'GREEN', 'OLIVE': 'OLIVE', 'MINT': 'MINT', 'FOREST': 'GREEN',
            'DUSTY OLIVE': 'OLIVE', 'ARMY': 'GREEN', 'KHAKI': 'KHAKI',
            'UNGU': 'PURPLE', 'EGGPLANT': 'PURPLE', 'VIOLET': 'PURPLE', 'GRAPE': 'PURPLE',
            'PINK': 'PINK', 'BABY PINK': 'PINK', 'DUSTY PINK': 'PINK', 'BLUSH ROSE': 'PINK',
            'ROSE': 'PINK', 'DUSTY ROSE': 'PINK', 'CORAL': 'CORAL', 'DUSTY CORAL': 'CORAL',
            'KUNING': 'YELLOW', 'LEMON': 'YELLOW', 'MOSTARD': 'YELLOW', 'MUSTARD': 'YELLOW', 'GOLD': 'GOLD',
            'ORANGE': 'ORANGE', 'TANGERINE': 'ORANGE', 'FANTA': 'ORANGE',
            'COKLAT': 'BROWN', 'CHOCOLATE': 'BROWN', 'COFFEE': 'BROWN', 'ESPRESSO': 'BROWN',
            'CINNAMON': 'BROWN', 'CARAMEL': 'BROWN', 'CAPPUCINO': 'BROWN', 'MOCCA': 'BROWN', 'CAMEL': 'BROWN',
            'ABU': 'GREY', 'ABU TUA': 'GREY', 'ABU MUDA': 'GREY', 'GREY': 'GREY', 'DARK GREY': 'GREY',
            'ASH': 'GREY', 'CLOUD GREY': 'GREY', 'DOVE GREY': 'GREY', 'FOG': 'GREY',
            'CREAM': 'CREAM', 'BEIGE': 'BEIGE', 'SAND': 'BEIGE', 'BONE': 'BEIGE',
            'BURGUNDY': 'BURGUNDY', 'MAHOGANY': 'BURGUNDY', 'WINE': 'BURGUNDY',
            'PALE MAUVE': 'MAUVE', 'DUSTY MAUVE': 'MAUVE', 'MAUVE': 'MAUVE', 'LILAC': 'LILAC',
            'PASTEL PINK': 'PINK', 'LIGHT PINK': 'PINK', 'DARK PINK': 'PINK',
            'LIGHT BLUE': 'BLUE', 'DARK BLUE': 'BLUE',
            'DARK GREEN': 'GREEN', 'LIGHT GREEN': 'GREEN',
            'LAVENDER': 'LAVENDER', 'DUSTY LAVENDER': 'LAVENDER',
            'PEACH': 'PEACH', 'DUSTY PEACH': 'PEACH',
            'TEAL': 'TEAL', 'TURQUOISE': 'TURQUOISE', 'AQUA': 'AQUA',
            'MAROON': 'MAROON', 'PLUM': 'PLUM',
            'TAN': 'TAN', 'WHEAT': 'WHEAT', 'FAWN': 'BEIGE',
            'INDIGO': 'INDIGO', 'DARK VIOLET': 'PURPLE',
            'BRONZE': 'BRONZE', 'COPPER': 'COPPER',
            'LIME': 'LIME', 'CORNFLOWER': 'BLUE'
        }
        
        return color_mappings.get(q)

    def _group_by_name(self, results):
        """Group results by name_product, combining sizes and stock."""
        from collections import defaultdict
        
        # Size ordering: XS -> XXL and beyond
        SIZE_ORDER = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', '3XL', '4XL', '5XL', '6XL', 'P0', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6', 'P7', 'P8', 'P9', 'P10', 'P11', 'P12']
        
        def sort_sizes(sizes):
            def size_key(s):
                for i, o in enumerate(SIZE_ORDER):
                    if s.upper() == o:
                        return i
                # For numbered sizes like P0, extract number
                if s.startswith('P'):
                    try:
                        return 100 + int(s[1:])
                    except:
                        return 200
                return 300  # Unknown sizes at end
            
            return sorted(sizes, key=size_key)
        
        grouped = defaultdict(lambda: {
            "sizes": [],
            "stock_per_size": {},
            "prices": set(),
            "product_id": None,
            "brand": None,
            "category": None,
            "color": None,
            "thumbnail": None,
            "sku": None,
            "description": None,
            "is_new": False,
            "discount_percent": 0,
            "weight_grams": 0,
            "min_stock": 0,
            "total_stock": 0
        })
        
        for r in results:
            name = r["name_product"]
            size = r.get("size", "")
            stock = r.get("stock", 0)
            
            g = grouped[name]
            g["product_id"] = r.get("product_id")
            g["brand"] = r.get("brand")
            g["category"] = r.get("category")
            g["color"] = r.get("color")
            g["thumbnail"] = r.get("thumbnail")
            g["sku"] = r.get("sku")
            g["description"] = r.get("description")
            g["is_new"] = r.get("is_new", False)
            g["discount_percent"] = r.get("discount_percent", 0)
            g["weight_grams"] = r.get("weight_grams", 0)
            
            if size and size not in g["sizes"]:
                g["sizes"].append(size)
                g["stock_per_size"][size] = stock
            
            g["prices"].add(r.get("price", 0))
            g["total_stock"] += stock
            if stock > 0:
                g["min_stock"] = max(g["min_stock"], 1)
        
        output = []
        for name, g in grouped.items():
            prices = list(g["prices"])
            # Sort sizes in logical order
            sorted_sizes = sort_sizes(g["sizes"])
            # Sort stock_per_size dict by size order
            sorted_stock = {s: g["stock_per_size"][s] for s in sorted_sizes if s in g["stock_per_size"]}
            output.append({
                "product_id": g["product_id"],
                "name_product": name,
                "brand": g["brand"],
                "category": g["category"],
                "sizes": sorted_sizes,
                "color": g["color"],
                "price": {"min": min(prices), "max": max(prices)} if prices else {"min": 0, "max": 0},
                "stock_per_size": sorted_stock,
                "stock": g["total_stock"],
                "in_stock": bool(g["min_stock"]),
                "thumbnail": g["thumbnail"],
                "sku": g["sku"],
                "description": g["description"],
                "is_new": g["is_new"],
                "discount_percent": g["discount_percent"],
                "weight_grams": g["weight_grams"]
            })
        
        return output

    def search_products_with_prediction(self, keyword=None, color=None, max_price=None, min_price=None, in_stock=True, only_new=False, only_discounted=False, size=None, feature=None, brand=None, category=None, sku=None, limit=10000, sort_by="newest"):
        """Search with automatic color prediction fallback. Returns exact matches first, then predicted color matches."""
        original_color = color
        predicted_color = self._predict_basic_color(color) if color else None
        
        results = []
        
        # Search 1: Exact color (user typed) - uses LIKE for partial matching
        if not original_color:
            # No color filter, just search once
            results = self._execute_search(
                keyword=keyword, color=None, max_price=max_price, min_price=min_price,
                in_stock=in_stock, only_new=only_new, only_discounted=only_discounted,
                size=size, feature=feature, brand=brand, category=category, sku=sku,
                limit=limit, sort_by=sort_by
            )
        else:
            exact_results = self._execute_search(
                keyword=keyword, color=original_color, max_price=max_price, min_price=min_price,
                in_stock=in_stock, only_new=only_new, only_discounted=only_discounted,
                size=size, feature=feature, brand=brand, category=category, sku=sku,
                limit=limit, sort_by=sort_by
            )
            results.extend(exact_results)
        
        # Search 2: Predicted basic color (only for extended colors like PALE MAUVE -> MAUVE)
        if predicted_color and predicted_color != original_color:
            predicted_results = self._execute_search(
                keyword=keyword, color=predicted_color, max_price=max_price, min_price=min_price,
                in_stock=in_stock, only_new=only_new, only_discounted=only_discounted,
                size=size, feature=feature, brand=brand, category=category, sku=sku,
                limit=limit, sort_by=sort_by
            )
            results.extend(predicted_results)
        
        # Group by name_product to combine sizes
        if results:
            results = self._group_by_name(results)
        
        # Sort results
        if results:
            if sort_by == "newest":
                results.sort(key=lambda x: x.get("is_new", False), reverse=True)
            elif sort_by == "price_low":
                results.sort(key=lambda x: x.get("price", {}).get("min", 0))
            elif sort_by == "price_high":
                results.sort(key=lambda x: x.get("price", {}).get("max", 0), reverse=True)
            elif sort_by == "name":
                results.sort(key=lambda x: x.get("name_product", ""))
            elif sort_by == "stock":
                results.sort(key=lambda x: x.get("stock", 0), reverse=True)
        
        return results

db = ProductDatabase()

if __name__ == "__main__":
    res = db.search_products(keyword="gamis", color="BLACK", max_price=250000)
    print(json.dumps(res, indent=2))