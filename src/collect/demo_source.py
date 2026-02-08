"""Demo data source — realistic product data for testing the full pipeline.

Uses real-world product examples from Chinese marketplaces.
This source is used to validate the pipeline while we build
proper scrapers (1688 requires headless browser).
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from src.models import RawProduct

from .base import BaseCollector

# Realistic product data based on actual trending items on Chinese marketplaces
DEMO_PRODUCTS: list[dict] = [
    {
        "title_cn": "无线蓝牙耳机 降噪 运动耳机 2025新款",
        "title_ru": "Беспроводные Bluetooth наушники с шумоподавлением, спортивные, новинка 2025",
        "category": "electronics",
        "price_cny": 28.5,
        "min_order": 50,
        "sales_volume": 15200,
        "sales_trend": 45.0,
        "rating": 4.7,
        "supplier_name": "Shenzhen AudioTech Co.",
        "supplier_years": 6,
        "source_url": "https://detail.1688.com/offer/demo-bt-earphones-001.html",
        "wb_keyword": "наушники беспроводные",
        "wb_est_price": 2500.0,
    },
    {
        "title_cn": "迷你投影仪 家用 高清 便携式 手机投影",
        "title_ru": "Мини-проектор портативный для дома, HD, подключение к телефону",
        "category": "electronics",
        "price_cny": 185.0,
        "min_order": 10,
        "sales_volume": 4800,
        "sales_trend": 78.0,
        "rating": 4.5,
        "supplier_name": "Guangzhou OptiView Technology",
        "supplier_years": 4,
        "source_url": "https://detail.1688.com/offer/demo-mini-projector-002.html",
        "wb_keyword": "мини проектор",
        "wb_est_price": 7500.0,
    },
    {
        "title_cn": "智能手表 心率监测 血氧检测 运动手环",
        "title_ru": "Смарт-часы с мониторингом пульса и уровня кислорода, фитнес-браслет",
        "category": "electronics",
        "price_cny": 42.0,
        "min_order": 30,
        "sales_volume": 22000,
        "sales_trend": 32.0,
        "rating": 4.6,
        "supplier_name": "Dongguan WearTech Ltd.",
        "supplier_years": 8,
        "source_url": "https://detail.1688.com/offer/demo-smart-watch-003.html",
        "wb_keyword": "смарт часы",
        "wb_est_price": 3200.0,
    },
    {
        "title_cn": "车载手机支架 磁吸 导航支架 汽车用品",
        "title_ru": "Автомобильный магнитный держатель для телефона, крепление для навигации",
        "category": "car_accessories",
        "price_cny": 8.5,
        "min_order": 100,
        "sales_volume": 35000,
        "sales_trend": 15.0,
        "rating": 4.8,
        "supplier_name": "Yiwu AutoParts Trading",
        "supplier_years": 11,
        "source_url": "https://detail.1688.com/offer/demo-car-holder-004.html",
        "wb_keyword": "держатель телефона авто",
        "wb_est_price": 550.0,
    },
    {
        "title_cn": "USB充电暖手宝 移动电源 二合一 冬季热销",
        "title_ru": "USB-грелка для рук + повербанк 2-в-1, зимний хит продаж",
        "category": "gadgets",
        "price_cny": 22.0,
        "min_order": 50,
        "sales_volume": 18500,
        "sales_trend": 120.0,
        "rating": 4.4,
        "supplier_name": "Shenzhen GiftPower Co.",
        "supplier_years": 5,
        "source_url": "https://detail.1688.com/offer/demo-hand-warmer-005.html",
        "wb_keyword": "грелка для рук",
        "wb_est_price": 1500.0,
    },
    {
        "title_cn": "电动牙刷 超声波 充电式 成人 防水",
        "title_ru": "Электрическая зубная щётка ультразвуковая, перезаряжаемая, водонепроницаемая",
        "category": "home",
        "price_cny": 35.0,
        "min_order": 20,
        "sales_volume": 12000,
        "sales_trend": 55.0,
        "rating": 4.6,
        "supplier_name": "Ningbo OralCare Technology",
        "supplier_years": 7,
        "source_url": "https://detail.1688.com/offer/demo-toothbrush-006.html",
        "wb_keyword": "электрическая зубная щетка",
        "wb_est_price": 2200.0,
    },
    {
        "title_cn": "宠物自动喂食器 智能 定时 猫粮狗粮",
        "title_ru": "Автоматическая кормушка для животных, умная, с таймером, для кошек и собак",
        "category": "home",
        "price_cny": 68.0,
        "min_order": 10,
        "sales_volume": 8900,
        "sales_trend": 95.0,
        "rating": 4.3,
        "supplier_name": "Foshan PetSmart Electronics",
        "supplier_years": 3,
        "source_url": "https://detail.1688.com/offer/demo-pet-feeder-007.html",
        "wb_keyword": "автокормушка кошка",
        "wb_est_price": 3800.0,
    },
    {
        "title_cn": "便携式榨汁杯 充电 随身 果汁机 小型",
        "title_ru": "Портативный блендер-бутылка, перезаряжаемый, мини-соковыжималка",
        "category": "home",
        "price_cny": 25.0,
        "min_order": 50,
        "sales_volume": 28000,
        "sales_trend": 40.0,
        "rating": 4.5,
        "supplier_name": "Zhongshan KitchenTech Co.",
        "supplier_years": 9,
        "source_url": "https://detail.1688.com/offer/demo-blender-008.html",
        "wb_keyword": "портативный блендер",
        "wb_est_price": 1800.0,
    },
    {
        "title_cn": "LED化妆镜 台式 带灯 触控调光 桌面镜",
        "title_ru": "LED-зеркало для макияжа настольное с подсветкой, сенсорная регулировка яркости",
        "category": "beauty_devices",
        "price_cny": 32.0,
        "min_order": 30,
        "sales_volume": 9500,
        "sales_trend": 60.0,
        "rating": 4.7,
        "supplier_name": "Shenzhen BeautyLight Ltd.",
        "supplier_years": 5,
        "source_url": "https://detail.1688.com/offer/demo-led-mirror-009.html",
        "wb_keyword": "зеркало с подсветкой",
        "wb_est_price": 2000.0,
    },
    {
        "title_cn": "太阳能户外灯 庭院灯 防水 感应灯 花园装饰",
        "title_ru": "Солнечный садовый светильник уличный, водонепроницаемый, с датчиком движения",
        "category": "outdoor",
        "price_cny": 15.0,
        "min_order": 100,
        "sales_volume": 42000,
        "sales_trend": 25.0,
        "rating": 4.4,
        "supplier_name": "Jiangmen SolarBright Co.",
        "supplier_years": 12,
        "source_url": "https://detail.1688.com/offer/demo-solar-light-010.html",
        "wb_keyword": "садовый светильник",
        "wb_est_price": 800.0,
    },
    {
        "title_cn": "无线充电器 桌面 快充 适用苹果安卓 折叠",
        "title_ru": "Беспроводная зарядка настольная, быстрая, для iPhone/Android, складная",
        "category": "phone_accessories",
        "price_cny": 18.0,
        "min_order": 50,
        "sales_volume": 31000,
        "sales_trend": 20.0,
        "rating": 4.6,
        "supplier_name": "Shenzhen ChargePro Technology",
        "supplier_years": 7,
        "source_url": "https://detail.1688.com/offer/demo-wireless-charger-011.html",
        "wb_keyword": "беспроводная зарядка",
        "wb_est_price": 1200.0,
    },
    {
        "title_cn": "颈挂式风扇 便携 USB充电 免手持 夏季爆款",
        "title_ru": "Шейный вентилятор портативный, USB-зарядка, hands-free, летний хит",
        "category": "gadgets",
        "price_cny": 19.5,
        "min_order": 50,
        "sales_volume": 55000,
        "sales_trend": 180.0,
        "rating": 4.3,
        "supplier_name": "Zhongshan CoolBreeze Ltd.",
        "supplier_years": 4,
        "source_url": "https://detail.1688.com/offer/demo-neck-fan-012.html",
        "wb_keyword": "вентилятор шейный",
        "wb_est_price": 1200.0,
    },
]


class DemoCollector(BaseCollector):
    """Returns realistic demo products for pipeline testing."""

    async def collect(self, category: str, limit: int = 20) -> list[RawProduct]:
        # Filter by category if specified, otherwise return all
        if category == "all":
            pool = DEMO_PRODUCTS
        else:
            pool = [p for p in DEMO_PRODUCTS if p.get("category") == category]
            if not pool:
                pool = DEMO_PRODUCTS  # fallback to all

        # Shuffle and limit
        selected = random.sample(pool, min(limit, len(pool)))

        products = []
        for item in selected:
            products.append(
                RawProduct(
                    source="demo",
                    source_url=item["source_url"],
                    title_cn=item["title_cn"],
                    title_ru=item["title_ru"],
                    category=item.get("category", ""),
                    price_cny=item["price_cny"],
                    min_order=item.get("min_order", 1),
                    sales_volume=item.get("sales_volume", 0),
                    sales_trend=item.get("sales_trend", 0),
                    rating=item.get("rating", 0),
                    supplier_name=item.get("supplier_name", ""),
                    supplier_years=item.get("supplier_years", 0),
                    wb_keyword=item.get("wb_keyword", ""),
                    wb_est_price=item.get("wb_est_price", 0.0),
                    collected_at=datetime.now(timezone.utc),
                )
            )

        return products
