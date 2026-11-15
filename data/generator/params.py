"""Generator parameters (DATA_AND_LOGIC section 4). Every tunable number lives here."""
from datetime import date, time

START = date(2026, 8, 1)
END = date(2026, 11, 14)  # inclusive
DEMO_DATE = date(2026, 11, 15)
MERCHANT_CREATED_AT = "2026-08-01T05:00:00+05:30"

# 4.2 merchant parameters: customer txns/day (Poisson), median sale (₹), lognormal sigma, clip (₹)
CATEGORY = {
    "VEGETABLES": {"lam": 35, "median": 120, "sigma": 0.8, "lo": 10, "hi": 2500},
    "FRUITS": {"lam": 30, "median": 180, "sigma": 0.75, "lo": 20, "hi": 3000},
    "FLOWERS": {"lam": 25, "median": 60, "sigma": 0.7, "lo": 10, "hi": 1500},
    "TEA_STALL": {"lam": 80, "median": 25, "sigma": 0.5, "lo": 10, "hi": 300},
    "MIXED_KIRANA": {"lam": 45, "median": 150, "sigma": 0.9, "lo": 10, "hi": 4000},
}
# Same proportions as the original 40 (12/10/6/6/6), scaled to 180 merchants (agreed 2026-11-14).
# Each group gets the proportions separately, so train and test both have every category.
TRAIN_CATEGORY_COUNTS = {"VEGETABLES": 21, "FRUITS": 18, "FLOWERS": 11, "TEA_STALL": 10, "MIXED_KIRANA": 10}
TEST_CATEGORY_COUNTS = {"VEGETABLES": 33, "FRUITS": 27, "FLOWERS": 17, "TEA_STALL": 17, "MIXED_KIRANA": 16}
TRAIN_MERCHANTS = [f"M{n}" for n in range(101, 171)]  # train + calibration (70)
TEST_MERCHANTS = [f"M{n}" for n in range(171, 281)]  # test, never seen (110)
EVAL_MERCHANTS = TRAIN_MERCHANTS + TEST_MERCHANTS  # M101-M280
EVAL_CATEGORY_COUNTS = {c: TRAIN_CATEGORY_COUNTS[c] + TEST_CATEGORY_COUNTS[c] for c in TRAIN_CATEGORY_COUNTS}
TEST_PERIOD = (date(2026, 10, 16), date(2026, 11, 14))  # inclusive
TARGET_TEST_FAMILY_PAYMENTS = 500
SCALE_RANGE = (0.6, 1.5)  # eval merchants only; demo merchants use 1.0
SUNDAY_FACTOR = 1.2

SHOP_OPEN = time(5, 30)
SHOP_CLOSE = time(21, 30)
PEAKS = [(time(6, 30), time(9, 30)), (time(17, 0), time(20, 0))]
PEAK_WEIGHT = 3.0  # arrival intensity in peak slots relative to off-peak

# 4.3 payer roles
REGULAR_POOL = 300
ZIPF_S = 1.1
CUSTOMER_P2M = 0.85
CUSTOMER_PERSONAL = 0.97
ROUND_TO_5 = 0.60
WALKIN_SHARE = 0.35
REGULAR_BIG_ORDER_SHARE = 0.03  # regulars: P2P with a round amount (paying for a bigger order)
REGULAR_BIG_ORDER_AMOUNT = (500, 2000)  # rounded to ₹100

BUSINESS_COUNT = (0, 3)
BUSINESS_GAP_DAYS = (1, 3)
BUSINESS_AMOUNT = (600, 3000)
BUSINESS_P2M = 0.90
BUSINESS_VPA = 0.70

BIG_ORDER_EVERY_DAYS = 14
BIG_ORDER_AMOUNT = (2000, 8000)
BIG_ORDER_P2P = 0.50
BIG_ORDER_ROUND_500 = 0.70

FAMILY_COUNT = (1, 4)
FAMILY_P2P = 0.85  # 15% P2M: the relative scans the shop QR
FAMILY_NON_ROUND = 0.25  # e.g. ₹750, ₹1,250, ₹2,350
FAMILY_AMOUNTS = [500, 1000, 1500, 2000, 3000, 5000]
FAMILY_GAP_DAYS = (5, 30)
FAMILY_EVENING = 0.65  # after 18:00; the other 35% during shop hours before 18:00

FRIEND_COUNT = (0, 2)
FRIEND_TIMES = (2, 4)
FRIEND_AMOUNTS = [500, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
FRIEND_NON_ROUND = 0.30
NON_ROUND_RANGE = (500, 5000)  # non-round family/friend amounts: multiples of ₹50 that are not multiples of ₹100

CREDIT_COUNT = (3, 8)  # credit-settlement customers (SALE): settle a tab weekly or monthly by P2P
CREDIT_GAP_DAYS = {"weekly": (6, 8), "monthly": (28, 32)}
CREDIT_AMOUNT = (500, 3000)  # rounded to ₹100
CREDIT_EVENING = 0.70

MIXED_MERCHANT_SHARE = 1 / 3
MIXED_SALE_SHARE = 0.30
MIXED_GAP_DAYS = (7, 21)

# 4.4 refunds, reversals
REFUND_RATE = 0.003  # of SALE payments
REFUND_FULL_SHARE = 0.5
REFUND_PARTIAL = (0.2, 0.8)
REFUND_MAX_DAYS = 2
REVERSAL_RATE = 0.001  # of all payments
REVERSAL_MAX_DAYS = 1

EXPENSE_VOICE_SHARE = 0.70
