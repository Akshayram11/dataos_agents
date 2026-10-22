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
    weight NUMERIC(10,2),
    material VARCHAR(50),
    model_number VARCHAR(50),
    sku VARCHAR(50),
    upc VARCHAR(20),
    price NUMERIC(10,2),
    cost NUMERIC(10,2),
    supplier VARCHAR(100),
    warranty_period VARCHAR(50),
    release_date DATE,
    rating NUMERIC(3,1),
    stock_quantity NUMERIC(38,0),
    discontinued BIT
  ),
  grain product_id
);
