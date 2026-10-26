-- 延迟根因拆解：卖家发货慢，还是物流运输慢？
-- 把订单按「卖家是否超时发货」分成两类，分别看延迟率、处理时长和运输时长
-- 再算每一类在全部延迟订单中的占比

WITH base AS (
    SELECT
        seller_late,
        COUNT(*)                         AS orders,
        SUM(is_late)                     AS late_orders,
        AVG(is_late)                     AS late_rate,
        AVG(handling_days)               AS avg_handling_days,
        AVG(transit_days)                AS avg_transit_days
    FROM dwd_delivered_orders
    GROUP BY seller_late
)
SELECT
    CASE seller_late WHEN 1 THEN '卖家超时发货' ELSE '卖家按时发货' END AS seller_handover,
    orders,
    ROUND(1.0 * orders / SUM(orders) OVER (), 4)            AS order_share,
    late_orders,
    ROUND(late_rate, 4)                                     AS late_rate,
    ROUND(1.0 * late_orders / SUM(late_orders) OVER (), 4)  AS share_of_all_late,
    ROUND(avg_handling_days, 2)                             AS avg_handling_days,
    ROUND(avg_transit_days, 2)                              AS avg_transit_days
FROM base
ORDER BY seller_late;
