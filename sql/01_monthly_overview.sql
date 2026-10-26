-- 月度经营概览：订单量、GMV（商品金额，不含运费）、客单价、环比
-- 技巧：CTE + LAG 窗口函数计算环比
-- 只统计 2017-01 ~ 2018-08：2016 年和 2018-09 之后的订单极少，不是完整业务月

WITH monthly AS (
    SELECT
        strftime('%Y-%m', o.order_purchase_timestamp) AS month,
        COUNT(DISTINCT o.order_id)                    AS orders,
        SUM(oi.price)                                 AS gmv
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    WHERE o.order_status NOT IN ('canceled', 'unavailable')
      AND o.order_purchase_timestamp >= '2017-01-01'
      AND o.order_purchase_timestamp <  '2018-09-01'
    GROUP BY 1
)
SELECT
    month,
    orders,
    ROUND(gmv, 2)                                   AS gmv,
    ROUND(gmv / orders, 2)                          AS aov,
    ROUND(100.0 * (gmv - LAG(gmv) OVER (ORDER BY month))
          / LAG(gmv) OVER (ORDER BY month), 2)      AS gmv_mom_pct
FROM monthly
ORDER BY month;
