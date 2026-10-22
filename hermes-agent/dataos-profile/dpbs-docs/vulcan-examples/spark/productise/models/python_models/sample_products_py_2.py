import typing as t

from pyspark.sql import functions as F

from vulcan import ExecutionContext, ModelKindName, model


@model(
    "gold_sparkv.sample_products_py_2",
    kind=dict(name=ModelKindName.FULL),
    description=(
        "PySpark example that writes product records with an ARRAY<DOUBLE> vector column "
        "to validate vector storage in Icebase/Iceberg."
    ),
    columns={
        "product_id": "int",
        "name": "string",
        "category": "string",
        "price": "decimal(10,2)",
        "product_vector": "array<double>",
        "icebase_vector_support_answer": "string",
    },
    grains=["product_id"],
    tags=["python", "spark", "vector", "icebase"],
    depends_on=["bronze_sparkv.products"],
    physical_properties={
        "format": "iceberg",
    },
)
def execute(context: ExecutionContext, **kwargs: t.Any):
    spark = context.spark
    if spark is None:
        raise RuntimeError("SparkSession is required for this model.")

    products_table = context.resolve_table("bronze_sparkv.products")
    products = spark.table(products_table)
    source_count = products.count()
    print(f"[sample_products_py_2] product rows={source_count}")
    if source_count == 0:
        raise RuntimeError(f"No rows found in {products_table}; aborting write.")

    return products.select(
        "product_id",
        "name",
        "category",
        "price",
        F.array(
            F.round(
                (F.pmod(F.col("product_id"), F.lit(1000)).cast("double") / F.lit(1000.0)),
                6,
            ),
            F.round((F.col("price").cast("double") / F.lit(1000.0)), 6),
            F.round(
                (
                    F.pmod(F.xxhash64(F.col("category")), F.lit(1000)).cast("double")
                    / F.lit(1000.0)
                ),
                6,
            ),
        ).alias("product_vector"),
        F.lit(
            "Yes. Store vectors in Icebase/Iceberg as ARRAY<DOUBLE> columns from PySpark."
        ).alias("icebase_vector_support_answer"),
    )
