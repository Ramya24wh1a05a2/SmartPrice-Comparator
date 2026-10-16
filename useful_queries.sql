-- Example queries on the SmartPrice database (run in MySQL Workbench / mysql shell after `USE smartprice;`)

-- 1. Cheapest stored price per product (JOIN + GROUP BY)
SELECT p.name, MIN(pp.typical_price) AS cheapest
FROM products p JOIN platform_prices pp ON pp.product_id = p.id
GROUP BY p.id, p.name ORDER BY cheapest;

-- 2. Cheapest store for each product (subquery)
SELECT p.name, pp.platform, pp.typical_price
FROM products p JOIN platform_prices pp ON pp.product_id = p.id
WHERE pp.typical_price = (SELECT MIN(typical_price) FROM platform_prices WHERE product_id = p.id);

-- 3. Daily lowest recorded live price for a product (real history chart data)
SELECT DATE(recorded_at) AS day, platform, MIN(price) AS lowest
FROM price_history WHERE product_key = 'pencil box'
GROUP BY day, platform ORDER BY day;

-- 4. Biggest price swing per product and store
SELECT product_key, platform, MIN(price) AS low, MAX(price) AS high, MAX(price) - MIN(price) AS swing
FROM price_history GROUP BY product_key, platform ORDER BY swing DESC;

-- 5. Pending alerts with the user's name (JOIN)
SELECT u.name, a.product_name, a.target_price, a.set_at
FROM price_alerts a JOIN users u ON u.id = a.user_id
WHERE a.fulfilled = 0 ORDER BY a.set_at;

-- 6. Most searched products
SELECT query, COUNT(*) AS searches FROM search_history GROUP BY query ORDER BY searches DESC LIMIT 10;

-- 7. Users with the number of alerts they set (LEFT JOIN)
SELECT u.email, COUNT(a.id) AS alerts
FROM users u LEFT JOIN price_alerts a ON a.user_id = u.id GROUP BY u.id, u.email;
