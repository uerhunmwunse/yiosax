import requests
import random

# from scraper import response


class RainforestAPI:
    def __init__(self,api_key):
        self.api_key = api_key
        self.base_url =  "https://api.rainforestapi.com/request"


    def merge(self,left,right):
        lst = []
        while len(left) != 0 and len(right) != 0:
            left_price = left[0].get("price", float("inf"))
            right_price = right[0].get("price", float("inf"))
            if isinstance(left_price,dict):
                left_price = left_price.get("value")
            if isinstance(right_price,dict):
                right_price = right_price.get("value")
            if left_price is None and right_price is None:
                left.pop(0)
                right.pop(0)
            elif left_price is None:
                left.pop(0)
            elif right_price is None:
                right.pop(0)
            elif left_price < right_price:
                lst.append(left.pop(0))
            else:
                lst.append(right.pop(0))

        lst.extend(left)
        lst.extend(right)
        return lst

    def merge_sort(self,lst):
        if len(lst) == 1:
            return lst
        else:
            mid = len(lst) // 2
            left = lst[:mid]
            right = lst[mid:]
            return self.merge(self.merge_sort(left),self.merge_sort(right))




    def is_real_mobile_product(self,title):
        title = title.lower()
        # unwanted = ["case","cover","screen protector","charger","cable","mount","stand"]
        blocked_keywords = [
            # Accessories
            "case", "cover", "screen protector", "charger", "cable", "wireless charger", "earbud", "earphones",
            "headphones",

            # Storage
            "usb", "flash drive", "memory stick", "sd card", "micro sd", "external storage",

            # Pens & Stylus
            "pen", "stylus", "touch pen",

            # Misc gadgets
            "tripod", "mount", "stand", "holder", "pop socket", "ring light", "camera lens",

            # SIM & Cards
            "sim card", "sim tool", "nano sim", "adapter",

            # Tablets & Smartwatches
            "tablet", "iPad", "watch", "smartwatch", "fitness tracker", "band",

            # Household/Random
            "remote", "fan", "lamp", "light bulb", "calculator", "speaker", "radio",

            # Toys & Knockoffs
            "toy", "kids phone", "fake phone", "learning phone",

            # Brands not phones
            "Logitech", "SanDisk", "Kingston", "TP-Link", "NETGEAR", "JBL", "Anker", "Bose"
        ]

        for i in blocked_keywords:
            if i in title:
                return False
        return True

    # def is_real_console_product(self, title):
    #     title = title.lower()
    #
    #     # Positive indicators - must have at least one of these
    #     console_keywords = [
    #         "playstation", "ps5", "xbox", "nintendo switch",
    #         "series x", "series s", "console", "system"
    #     ]
    #
    #     # Negative indicators - must not have any of these
    #     accessory_keywords = [
    #         "controller", "case", "cover", "skin", "charger", "dock",
    #         "headset", "earbud", "headphone", "remote", "stand", "mount",
    #         "game", "disc", "edition", "digital code", "subscription",
    #         "blu-ray", "memory card", "gift card", "bundle"
    #     ]
    #
    #     # Check for positive indicators
    #     has_console_keyword = any(kw in title for kw in console_keywords)
    #
    #     # Check for accessory indicators
    #     has_accessory_keyword = any(kw in title for kw in accessory_keywords)
    #
    #     # It's a console if:
    #     # 1. Has a console keyword AND
    #     # 2. Does NOT have accessory keywords
    #     return has_console_keyword and not has_accessory_keyword

    def is_real_console_product(self, title):
        title = title.lower()
        blocked_keywords = [
            # Accessories and peripherals
            "controller", "charging dock", "accessory", "cable", "adapter",
            "headset", "skin", "cover", "case", "joystick", "keyboard", "monitor",
            "memory card", "gift card", "remote", "stand", "cooler", "fan", "mount",

            # Game-related terms
            "game", "disc", "edition", "deluxe", "ultimate", "collector",
            "launch", "remastered", "digital", "code", "playstation hits", "subscription",
            "software", "cartridge", "bundle", "set", "blu-ray",

            # Known PS/Xbox/Nintendo game titles and game studios
            "astro bot", "god of war", "spider-man", "elden ring", "call of duty",
            "fifa", "nba", "horizon", "death stranding", "gta", "minecraft", "fortnite",
            "ghost song", "tekken", "mortal kombat", "battlefield", "witcher", "resident evil",
            "bandai", "ubisoft", "rockstar", "capcom", "ea sports", "asobi", "studio", "square enix"
        ]

        valid_console_names = [
            "playstation 5 console", "ps5 console", "xbox series x console",
            "xbox console", "xbox series s", "nintendo switch console"
        ]

        if not any(console in title for console in valid_console_names):
            return False
        return True


        # for word in blocked_keywords:
        #     if word in title:
        #         return False
        # return True

    def is_real_laptop_product(self, title):
        title = title.lower()
        blocked_keywords = [
            # Accessories (explicit ones only)
            "laptop case", "sleeve", "keyboard cover", "screen protector", "cooling pad",
            "mount", "docking station", "usb hub", "mouse only", "keyboard only",
            "external hard drive", "external ssd", "webcam only", "microphone only",

            # Components as standalone items (not inside laptops)
            "ram module", "memory module", "barebone ssd", "barebone hdd", "graphics card", "motherboard", "cpu only",
            "processor only",

            # Non-laptop devices
            "tablet", "ipad", "chromebook", "netbook", "surface go", "surface pro", "kindle",

            # Brands that don’t sell laptops
            "logitech", "sandisk", "kingston", "tp-link", "netgear", "jbl", "anker", "bose", "asus router",

            # Other electronics
            "battery replacement", "power adapter", "charger only", "stylus pen", "drawing tablet",
            "projector", "printer", "scanner", "monitor only", "screen extender", "ethernet cable",

            # Toys or fake items
            "toy", "kids laptop", "learning computer", "fake laptop", "replica laptop", "training toy",

            # Home items
            "lamp", "fan", "calculator", "radio", "speaker only", "router", "switch", "modem"
        ]

        for keyword in blocked_keywords:
            if keyword in title:
                return False
        return True

    def _clean_and_dedup_filters(self,filters):
        normalized = [x.strip().lower() for x in filters if x and x != "Skip"]
        seen = set()
        deduped = []
        for f in normalized:
            if f not in seen:
                deduped.append(f)
                seen.add(f)
        return deduped

    def _parse_price(self, price_str):
        """
        Converts price strings like "$1,299.99" into float: 1299.99
        Returns None if price is missing or invalid.
        """
        if price_str:
            try:
                return float(price_str.replace("$", "").replace(",", "").strip())
            except Exception:
                return None
        return None



    def _search_console_product(self,category,product_name,manufacturer):
        console_filters = []
        random_page = random.randint(1, 5)

        if manufacturer != "Skip Manufacturer":
            console_filters.append(manufacturer.strip())

        if product_name:
            console_filters.append(product_name.strip())

        if len(console_filters) < 1:
            return None

        query = ' '.join(console_filters).strip()

        params = {
            "api_key": self.api_key,
            "type": "search",
            "amazon_domain": "amazon.ca",
            "search_term": query
        }

        response = requests.get(self.base_url, params=params)

        if response.status_code != 200:
            print(self.api_key)
            print("Rainforest API error:", response.status_code)
            return None

        data = response.json()
        results = data.get("search_results", [])

        if not results:
            print("❌ No console products found.")
            return None

        valid_products = []
        for item in results[:10]:
            title = item.get("title", "No title")
            if self.is_real_console_product(title):
                valid_products.append(item)

        print(valid_products)
        return valid_products, query

    def _search_laptop_product(self,category,product_name,manufacturer,ram,storage,processor,price):
        laptop_filters = []
        if manufacturer != "Skip Manufacturer":
            laptop_filters.append(manufacturer.strip())

        if product_name:
            laptop_filters.append(product_name.strip())

        # if model != "Skip Model":
        #     laptop_filters.append(model.strip())

        if processor != "Skip Processor":
            laptop_filters.append(processor.strip())

        if ram != "Skip RAM":
            laptop_filters.append(ram.strip())

        if storage != "Skip Storage":
            laptop_filters.append(storage.strip())

        if len(laptop_filters) < 2:
            return None

        cleaned_filters = self._clean_and_dedup_filters(laptop_filters)

        laptop_query = ' '.join(cleaned_filters).strip()

        params = {
            "api_key": self.api_key,
            "type": "search",
            "amazon_domain": "amazon.ca",
            "search_term": laptop_query
        }
        response1 = requests.get(self.base_url, params=params)
        if response1.status_code != 200:
            print("Rainforest API error:", response1.status_code)
            return None

        data = response1.json()
        results = data.get("search_results", [])
        if not results:
            print("❌ No results found.")
            return None
        valid_products = []
        for i, item in enumerate(results[:10]):
            title = item.get("title", "No title")
            print(title)
            if self.is_real_laptop_product(title):
                valid_products.append(item)
        print(valid_products,laptop_query)
        return valid_products,laptop_query

    def _search_mobile_product(self,category,product_name,manufacturer,model_name,storage,target_price):
        filters = []
        random_page = random.randint(1,5)
        # if category:
        #     category_term = self.category_keywords.get(category, "")
        #     filters.append(category_term)
        if manufacturer != "Skip Manufacturer":
            filters.append(manufacturer.strip())

        if product_name:
            filters.append(product_name.strip())

        if model_name != "Skip Model":
            filters.append(model_name.strip())

        if storage != "Skip Storage":
            filters.append(storage)

        if len(filters) < 2:
            return

        query = ' '.join(filters).strip()

        params = {
            "api_key": self.api_key,
            "type": "search",
            "amazon_domain": "amazon.ca",
            "search_term": query
        }

        response = requests.get(self.base_url, params=params)

        if response.status_code != 200:
            print("Rainforest API error:", response.status_code)
            return None

        data = response.json()
        results = data.get("search_results", [])

        if not results:
            print("❌ No results found.")
            return None
        valid_products = []
        for i, item in enumerate(results[:10]):
            title = item.get("title", "No title")
            if self.is_real_mobile_product(title):
                valid_products.append(item)
        print(valid_products)
        return valid_products,query



    def track_product(self,search_query,target_price,categoty):
        params = {
            "api_key": self.api_key,
            "type": "search",
            "amazon_domain": "amazon.ca",
            "search_term": search_query
        }

        response = requests.get(self.base_url, params=params)

        if response.status_code != 200:
            print("Rainforest API error:", response.status_code)
            return None

        search_data = response.json()
        search_products = search_data.get("search_results", [])
        print(f"🔍 Query: {search_query}")
        print(f"Found {len(search_products)} products.")

        if not search_products:
            print("❌ No results found.")
            return None
        valid_products = []
        if categoty ==  "Phones":
            for index in range(0,len(search_products)):
                title = search_products[index].get("title", "No title")
                if self.is_real_mobile_product(title):
                    valid_products.append(search_products[index])
        elif categoty == "Laptops":
            for index in range(0,len(search_products)):
                title = search_products[index].get("title", "No title")
                if self.is_real_laptop_product(title):
                    valid_products.append(search_products[index])
        elif categoty == "Gaming":
            for index in range(0,len(search_products)):
                title = search_products[index].get("title", "No title")
                if self.is_real_console_product(title):
                    valid_products.append(search_products[index])
        print(f"found {len(valid_products)} valid products")
        sorted_lst = self.merge_sort(valid_products)
        target_results = []
        for items in sorted_lst:
            current_price = items.get("price")
            if isinstance(current_price,dict):
                current_price = current_price.get("value")
            else:
                current_price = None

            if current_price is None:
                continue

            if current_price <= target_price:
                target_results.append(items)
            else:
                break
        return target_results




