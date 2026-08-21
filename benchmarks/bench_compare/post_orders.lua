-- wrk2 request script for POST /orders.
-- Body is the exact bytes used by verify_identical.py / the Locust files,
-- so every framework gets an identical request.
wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.body = '{"customer":"Acme Corp","items":[{"sku":"SKU-0001","qty":2,"price":1.25},{"sku":"SKU-0002","qty":5,"price":3.75}]}'
