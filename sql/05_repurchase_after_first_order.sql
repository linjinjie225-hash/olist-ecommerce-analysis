-- 首单是否延迟，会不会影响 180 天内复购？
--
-- 口径
--   用 customer_unique_id 识别同一个真实用户（customer_id 每单都会变）
--   首单：该用户最早一次下单（ROW_NUMBER，同一时刻多单时按 order_id 取一单）
--   复购：之后在「更晚的时刻」又下了单。
--         注意：有 290 个用户在同一秒下了多笔订单（一次购物被拆成多单），
--         这不是复购。如果直接用 LEAD 取下一单，会把它们误算成「0 天复购」。
--   观察窗口截断：数据到 2018-08 底，只保留 2018-03-04 之前下的首单，
--               保证每个用户都有完整的 180 天观察期（否则近期用户复购会被低估）
--   首单必须是已送达订单，才能判断是否延迟

WITH customer_orders AS (
    SELECT c.customer_unique_id, o.order_id, o.order_purchase_timestamp AS ts
    FROM orders o
    JOIN customers c ON c.customer_id = o.customer_id
),
ranked AS (
    SELECT
        customer_unique_id,
        order_id,
        ts,
        ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY ts, order_id) AS rn
    FROM customer_orders
),
next_purchase AS (
    -- 每个用户在首单时刻之后的第一次下单时间
    SELECT r.customer_unique_id, MIN(co.ts) AS next_ts
    FROM ranked r
    JOIN customer_orders co
      ON co.customer_unique_id = r.customer_unique_id
     AND co.ts > r.ts
    WHERE r.rn = 1
    GROUP BY r.customer_unique_id
),
first_orders AS (
    SELECT
        r.customer_unique_id,
        d.is_late,
        CASE WHEN julianday(n.next_ts) - julianday(r.ts) <= 180 THEN 1 ELSE 0 END AS repurchase_180d
    FROM ranked r
    JOIN dwd_delivered_orders d ON d.order_id = r.order_id
    LEFT JOIN next_purchase n  ON n.customer_unique_id = r.customer_unique_id
    WHERE r.rn = 1
      AND r.ts < '2018-03-04'
)
SELECT
    CASE is_late WHEN 1 THEN '首单延迟' ELSE '首单准时' END AS first_order,
    COUNT(*)                         AS customers,
    SUM(repurchase_180d)             AS repurchasers,
    ROUND(AVG(repurchase_180d), 5)   AS repurchase_rate_180d
FROM first_orders
GROUP BY is_late
ORDER BY is_late;
