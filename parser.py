import asyncio
import httpx
import random
import logging
import pandas as pd

from get_token import get_token
from image_basket import get_basket

logging.basicConfig(level=logging.INFO)

SEARCH_URL = "https://www.wildberries.ru/__internal/u-search/exactmatch/sng/common/v18/search"

HEADERS = {
    'accept': '*/*',
    'user-agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X)',
    'x-requested-with': 'XMLHttpRequest'
}

QUERY = "пальто из натуральной шерсти"


class WBParser:
    def __init__(self, cookies):
        self.cookies = cookies
        self.headers = HEADERS
        self.semaphore = asyncio.Semaphore(5)

        self.all_products = []
        self.filtered_products = []
        self.seen_ids = set()


    # Получаем страницу по запросу
    async def safe_request(self, client, params):
        for _ in range(3):
            try:
                async with self.semaphore:
                    await asyncio.sleep(random.uniform(0.2, 0.6))
                    resp = await client.get(
                        SEARCH_URL,
                        params=params,
                        cookies=self.cookies,
                        headers=self.headers,
                        timeout=15
                    )
                    if resp.status_code == 200:
                        return resp.json()
            except Exception as e:
                logging.error(e)
                await asyncio.sleep(1)
        return None


    # Формируем параметры запроса
    def build_params(self, page, min_price, max_price):
        return {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",
            "lang": "ru",
            "page": str(page),
            "resultset": "catalog",
            "sort": "popular",
            "spp": "30",
            "query": QUERY,
            "priceU": f"{int(min_price*100)};{int(max_price*100)}"
        }


    # Получаем карточку товара
    async def get_details(self, client, product):
        product_id = product.get("id")

        short_id = product_id // 100000
        part = product_id // 1000
        basket = get_basket(short_id)

        url = f'https://basket-{basket}.wbbasket.ru/vol{short_id}/part{part}/{product_id}/info/ru/card.json'

        try:
            async with self.semaphore:
                resp = await client.get(url, cookies=self.cookies, headers=self.headers, timeout=10)
                if resp.status_code != 200:
                    return None
                data = resp.json()
        except:
            return None

        description = data.get("description")
        features = data.get("grouped_options")

        price = product.get("sizes", [])[0].get("price", {}).get("product", 0) / 100

        details = {
            "Ссылка на товар": f"https://www.wildberries.ru/catalog/{product_id}/detail.aspx",
            "Артикул": product_id,
            "Название": product.get("name"),
            "Цена": f"{price} ₽",
            "Описание": description,
            "Ссылки на изображения": self.get_images(product),
            "Характеристики": features,
            "Название селлера": product.get("supplier"),
            "Ссылка на селлера": f"https://www.wildberries.ru/seller/{product.get('supplierId')}",
            "Размеры товара": ", ".join(size.get("name") for size in product.get("sizes", [])),
            "Остатки по товару": product.get("totalQuantity"),
            "Рейтинг": product.get("reviewRating"),
            "Количество отзывов": product.get("feedbacks"),
        }

        return details, price, product.get("reviewRating"), features


    # Формируем ссылки на изображения
    def get_images(self, product):
        prod_id = product.get("id")
        short_id = prod_id // 100000
        part = prod_id // 1000
        basket = get_basket(short_id)

        base_url = f'https://basket-{basket}.wbbasket.ru/vol{short_id}/part{part}/{prod_id}/images/big/'
        pics = product.get("pics", 0)

        return ",".join(base_url + f"{i}.webp" for i in range(1, pics + 1))


    # Проверяем страну производства
    def is_russia(self, features):
        if not features:
            return False
        for group in features:
            for opt in group.get("options", []):
                if "страна" in opt.get("name", "").lower() and "россия" in opt.get("value", "").lower():
                    return True
        return False


    # Парсинг диапазона
    async def parse_range(self, client, min_price, max_price):
        logging.info(f"Диапазон {min_price}-{max_price}")

        page = 1
        empty_streak = 0

        while True:
            params = self.build_params(page, min_price, max_price)
            data = await self.safe_request(client, params)

            if not data:
                break

            products = data.get("products", [])

            if not products:
                empty_streak += 1
                if empty_streak >= 2:
                    break
                page += 1
                continue

            empty_streak = 0

            tasks = []
            for p in products:
                pid = p.get("id")
                if pid in self.seen_ids:
                    continue
                self.seen_ids.add(pid)
                tasks.append(self.get_details(client, p))

            results = await asyncio.gather(*tasks)

            for res in results:
                if not res:
                    continue

                details, price, rating, features = res
                self.all_products.append(details)

                if price <= 10000 and rating and rating >= 4.5 and self.is_russia(features):
                    self.filtered_products.append(details)

            page += 1
            await asyncio.sleep(random.uniform(0.5, 1.2))


    # Выбор диапазона
    async def smart_parse(self, client, min_price, max_price):
        params = self.build_params(1, min_price, max_price)
        data = await self.safe_request(client, params)

        if not data:
            return

        total = data.get("total", 0)

        # Если слишком много товаров — делим
        if total > 1000:
            mid = (min_price + max_price) / 2
            await self.smart_parse(client, min_price, mid)
            await self.smart_parse(client, mid, max_price)
        else:
            await self.parse_range(client, min_price, max_price)


    # Запуск парсинга
    async def run(self):
        async with httpx.AsyncClient() as client:
            await self.smart_parse(client, 0, 360000)

        return self.filtered_products, self.all_products


# Сохранение в Excel
def save_excel(filtered, all_products):
    pd.DataFrame(filtered).to_excel("wb_filtered.xlsx", index=False)
    pd.DataFrame(all_products).to_excel("wb_all.xlsx", index=False)


# Запуск программы
if __name__ == "__main__":
    token = get_token()
    cookies = {"x_wbaas_token": token}

    parser = WBParser(cookies)

    loop = asyncio.get_event_loop()
    filtered, all_products = loop.run_until_complete(parser.run())

    save_excel(filtered, all_products)

    logging.info(f"Всего собрано товаров: {len(all_products)}")
    logging.info(f"Отфильтрованные товары: {len(filtered)}")