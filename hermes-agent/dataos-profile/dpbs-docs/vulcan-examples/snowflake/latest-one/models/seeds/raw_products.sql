MODEL (
  name lenovo.raw.raw_products,
  kind SEED (
    path '../../seeds/raw_products.csv'
  ),
  description 'Seed model loading raw product data from CSV file',
  tags ('seed', 'raw', 'product', 'catalog'),
  terms ('product.catalog', 'product.inventory'),
  columns (
    PRODUCT_ID VARCHAR(10),
    PRODUCT_NAME VARCHAR(100),
    CATEGORY VARCHAR(50),
    SUBCATEGORY VARCHAR(50),
    BRAND VARCHAR(50),
    COLOR VARCHAR(20),
    SIZE VARCHAR(20),
    WEIGHT NUMBER(10,2),
    MATERIAL VARCHAR(50),
    MODEL_NUMBER VARCHAR(50),
    SKU VARCHAR(50),
    UPC VARCHAR(20),
    PRICE NUMBER(10,2),
    COST NUMBER(10,2),
    SUPPLIER VARCHAR(100),
    WARRANTY_PERIOD VARCHAR(50),
    RELEASE_DATE DATE,
    RATING NUMBER(3,1),
    STOCK_QUANTITY NUMBER(38,0),
    DISCONTINUED BOOLEAN
  ),
  grain PRODUCT_ID
);
