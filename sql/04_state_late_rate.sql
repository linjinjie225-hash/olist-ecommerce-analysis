-- 各州的延迟率与运输时长排名（订单量 >= 300 的州，避免小样本排名失真）
-- 技巧：RANK() 窗口函数

WITH s AS (
    SELECT
        customer_state,
        COUNT(*)                           AS orders,
        AVG(is_late)                       AS late_rate,
        AVG(transit_days)                  AS avg_transit_days,
        AVG(CASE WHEN review_score <= 2 THEN 1.0 WHEN review_score IS NOT NULL THEN 0.0 END) AS bad_review_rate
    FROM dwd_delivered_orders
    GROUP BY customer_state
    HAVING COUNT(*) >= 300
)
SELECT
    customer_state,
    orders,
    ROUND(late_rate, 4)          AS late_rate,
    ROUND(avg_transit_days, 1)   AS avg_transit_days,
    ROUND(bad_review_rate, 4)    AS bad_review_rate,
    RANK() OVER (ORDER BY late_rate DESC) AS late_rank
FROM s
ORDER BY late_rank;
