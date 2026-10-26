-- 公共层：最新评价视图 + 已送达订单宽表（dwd_delivered_orders）
-- 后续所有分析都基于这张宽表，保证口径一致。
-- 宽表物化成实体表而不是视图：视图在多次 JOIN / 窗口函数里会被反复计算，非常慢。
--
-- 口径说明
--   已送达订单：order_status = 'delivered' 且有实际送达时间、交给物流时间
--   延迟：按「天」比较，实际送达日期 > 承诺送达日期
--   卖家超时发货：交给物流的时间 > 该订单所有商品中最晚的发货截止时间
--   评价：一个订单可能有多条评价，取最后一次回复的那条

DROP VIEW IF EXISTS v_latest_review;
CREATE VIEW v_latest_review AS
SELECT order_id, review_score
FROM (
    SELECT
        order_id,
        review_score,
        ROW_NUMBER() OVER (
            PARTITION BY order_id
            ORDER BY review_answer_timestamp DESC, review_creation_date DESC
        ) AS rn
    FROM order_reviews
)
WHERE rn = 1;

DROP TABLE IF EXISTS dwd_delivered_orders;
CREATE TABLE dwd_delivered_orders AS
WITH item_limit AS (
    SELECT
        order_id,
        MAX(shipping_limit_date) AS shipping_limit,
        SUM(price)               AS items_value,
        SUM(freight_value)       AS freight_value,
        COUNT(*)                 AS n_items
    FROM order_items
    GROUP BY order_id
)
SELECT
    o.order_id,
    c.customer_unique_id,
    c.customer_state,
    o.order_purchase_timestamp,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    il.items_value,
    il.freight_value,
    il.n_items,
    -- 延迟天数：正数 = 晚到几天，负数 = 提前几天
    CAST(julianday(date(o.order_delivered_customer_date))
         - julianday(date(o.order_estimated_delivery_date)) AS INTEGER) AS delay_days,
    CASE WHEN date(o.order_delivered_customer_date) > date(o.order_estimated_delivery_date)
         THEN 1 ELSE 0 END AS is_late,
    CASE WHEN o.order_delivered_carrier_date > il.shipping_limit
         THEN 1 ELSE 0 END AS seller_late,
    julianday(o.order_delivered_carrier_date) - julianday(o.order_approved_at)       AS handling_days,
    julianday(o.order_delivered_customer_date) - julianday(o.order_delivered_carrier_date) AS transit_days,
    r.review_score
FROM orders o
JOIN customers c   ON c.customer_id = o.customer_id
JOIN item_limit il ON il.order_id = o.order_id
LEFT JOIN v_latest_review r ON r.order_id = o.order_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_delivered_carrier_date IS NOT NULL;

CREATE INDEX idx_dwd_order    ON dwd_delivered_orders(order_id);
CREATE INDEX idx_dwd_customer ON dwd_delivered_orders(customer_unique_id);
