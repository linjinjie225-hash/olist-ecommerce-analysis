-- 卖家超时发货的帕累托分析：少数卖家是否贡献了大部分超时发货？
-- 订单按「第一个商品的卖家」归属（约 99% 的订单只有一个卖家）
-- 技巧：SUM() OVER (ORDER BY ...) 计算累计占比

WITH order_seller AS (
    SELECT order_id, seller_id
    FROM (
        SELECT order_id, seller_id,
               ROW_NUMBER() OVER (PARTITION BY order_id ORDER BY order_item_id) AS rn
        FROM order_items
    )
    WHERE rn = 1
),
seller_stats AS (
    SELECT
        os.seller_id,
        COUNT(*)            AS orders,
        SUM(d.seller_late)  AS seller_late_orders,
        AVG(d.seller_late)  AS seller_late_rate
    FROM dwd_delivered_orders d
    JOIN order_seller os ON os.order_id = d.order_id
    GROUP BY os.seller_id
),
ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (ORDER BY seller_late_orders DESC, orders DESC)  AS rank_by_late,
        COUNT(*) OVER ()                                                   AS n_sellers,
        SUM(seller_late_orders) OVER (ORDER BY seller_late_orders DESC, orders DESC
                                      ROWS UNBOUNDED PRECEDING)            AS cum_late,
        SUM(seller_late_orders) OVER ()                                    AS total_late,
        SUM(orders) OVER (ORDER BY seller_late_orders DESC, orders DESC
                          ROWS UNBOUNDED PRECEDING)                        AS cum_orders,
        SUM(orders) OVER ()                                                AS total_orders
    FROM seller_stats
)
SELECT
    rank_by_late,
    seller_id,
    orders,
    seller_late_orders,
    ROUND(seller_late_rate, 4)                     AS seller_late_rate,
    ROUND(1.0 * rank_by_late / n_sellers, 4)       AS cum_seller_share,
    ROUND(1.0 * cum_late / total_late, 4)          AS cum_late_share,
    ROUND(1.0 * cum_orders / total_orders, 4)      AS cum_order_share
FROM ranked
ORDER BY rank_by_late;
