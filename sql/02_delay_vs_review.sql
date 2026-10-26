-- 送达时间（相对承诺日期）与评分的关系
-- 差评定义：1~2 星
-- 只统计有评分的已送达订单

SELECT
    CASE
        WHEN delay_days <= -10 THEN '01 提前10天以上'
        WHEN delay_days <=  -5 THEN '02 提前5~9天'
        WHEN delay_days <=   0 THEN '03 提前0~4天'
        WHEN delay_days <=   3 THEN '04 延迟1~3天'
        WHEN delay_days <=   7 THEN '05 延迟4~7天'
        WHEN delay_days <=  14 THEN '06 延迟8~14天'
        ELSE                        '07 延迟15天以上'
    END                                                   AS delay_bucket,
    COUNT(*)                                              AS orders,
    ROUND(AVG(review_score), 3)                           AS avg_score,
    ROUND(AVG(CASE WHEN review_score <= 2 THEN 1.0 ELSE 0 END), 4) AS bad_review_rate,
    ROUND(AVG(CASE WHEN review_score = 5 THEN 1.0 ELSE 0 END), 4)  AS five_star_rate
FROM dwd_delivered_orders
WHERE review_score IS NOT NULL
GROUP BY 1
ORDER BY 1;
