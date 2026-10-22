MODEL (
  name raw.raw_products,
  kind SEED (
    path '../../seeds/raw_products.csv'
  ),
  description 'Seed model loading raw product data from csv file',
  tags ('seed', 'raw', 'product', 'catalog'),
  terms ('product.catalog', 'product.inventory'),
  columns (
    product_id VARCHAR(10),
    product_name VARCHAR(100),
    category VARCHAR(50),
    subcategory VARCHAR(50),
    brand VARCHAR(50),
    color VARCHAR(20),
    size VARCHAR(20),
    weight DOUBLE,
    material VARCHAR(50),
    model_number VARCHAR(50),
    sku VARCHAR(50),
    upc VARCHAR(20),
    price DOUBLE,
    cost DOUBLE,
    supplier VARCHAR(100),
    warranty_period VARCHAR(50),
    release_date DATE,
    rating DOUBLE,
    stock_quantity INT,
    discontinued BOOLEAN
  ),
  grain product_id
);
