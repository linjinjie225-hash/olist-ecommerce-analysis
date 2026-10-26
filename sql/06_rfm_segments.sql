-- 用户分层（改良版 RFM）
--
-- 为什么不用标准 RFM 五分位：Olist 约 97% 的用户只买过一次，F 几乎全是 1，
-- 对 F 做 NTILE(5) 没有意义。所以改成：
--   F：是否复购（>= 2 单）
--   R：最近一次购买距观察日（2018-09-01）是否在 180 天内
--   M：累计实付金额是否处于前 20%（NTILE(5) = 1）
--
-- 金额用 order_payments.payment_value（含运费、分期等实际支付）
-- 频次按「不同的下单时刻」计数：同一秒被拆成多单的购物算 1 次，不算复购
-- 只统计已送达订单

WITH customer_orders AS (
    SELECT
        d.customer_unique_id,
        d.order_id,
        d.order_purchase_timestamp,
        p.payment_value
    FROM dwd_delivered_orders d
    JOIN (SELECT order_id, SUM(payment_value) AS payment_value FROM order_payments GROUP BY order_id) p
      ON p.order_id = d.order_id
),
rfm AS (
    SELECT
        customer_unique_id,
        CAST(julianday('2018-09-01') - julianday(MAX(order_purchase_timestamp)) AS INTEGER) AS recency_days,
        COUNT(DISTINCT order_purchase_timestamp) AS frequency,
        SUM(payment_value)        AS monetary
    FROM customer_orders
    GROUP BY customer_unique_id
),
scored AS (
    SELECT
        *,
        NTILE(5) OVER (ORDER BY monetary DESC) AS m_quintile
    FROM rfm
)
SELECT
    CASE
        WHEN frequency >= 2                               THEN '1 复购用户'
        WHEN recency_days <= 180 AND m_quintile = 1       THEN '2 近期高价值新客'
        WHEN recency_days <= 180                          THEN '3 近期普通新客'
        WHEN m_quintile = 1                               THEN '4 沉睡高价值'
        ELSE                                                   '5 沉睡普通'
    END                                   AS segment,
    COUNT(*)                              AS customers,
    ROUND(1.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 4)            AS customer_share,
    ROUND(SUM(monetary), 2)                                       AS total_value,
    ROUND(SUM(monetary) / SUM(SUM(monetary)) OVER (), 4)          AS value_share,
    ROUND(AVG(monetary), 2)                                       AS avg_value,
    ROUND(AVG(recency_days), 1)                                   AS avg_recency_days,
    ROUND(AVG(frequency), 2)                                      AS avg_frequency
FROM scored
GROUP BY 1
ORDER BY 1;
