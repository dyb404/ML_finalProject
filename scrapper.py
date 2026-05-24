import time, csv, random, re, pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

BASE_URL    = "https://www.zameen.com/Homes/Islamabad-3-{}.html"
TARGET      = 399
OUTPUT_FILE = "zameen_islamabad.csv"

def setup_driver():
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": """
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = {runtime: {}};
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    """})
    return driver

def scroll_down(driver):
    h = driver.execute_script("return document.body.scrollHeight")
    for y in range(0, h, 500):
        driver.execute_script(f"window.scrollTo(0, {y});")
        time.sleep(0.04)
    time.sleep(1.5)

def get_listing_urls(driver, page_url):
    try:
        driver.get(page_url)
        WebDriverWait(driver, 35).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li[role='article']"))
        )
    except TimeoutException:
        print("  [!] Timeout — saving debug_page.html")
        with open("debug_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        return []

    scroll_down(driver)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    urls = []

    for article in soup.select("li[role='article']"):
        a = article.select_one("a.d870ae17")
        if not a:
            a = article.select_one("a[href*='/Property/']")
        if a and a.get("href"):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://www.zameen.com" + href
            urls.append(href)

    return list(set(urls))

def parse_detail(driver, url):
    try:
        driver.get(url)
        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        time.sleep(random.uniform(1.5, 3.0))
    except TimeoutException:
        print(f"    [!] Timeout: {url[:60]}")
        return None

    soup = BeautifulSoup(driver.page_source, "html.parser")
    d = {"url": url, "city": "Islamabad"}
#price
    price_el = soup.select_one("span[aria-label='Price']")
    if not price_el:
        
        for el in soup.find_all("span"):
            t = el.get_text(strip=True)
            if ("Crore" in t or "Lakh" in t) and len(t) < 30:
                price_el = el
                break
    d["price"] = price_el.get_text(strip=True) if price_el else None

#title
    h1 = soup.select_one("h1")
    d["title"] = h1.get_text(strip=True) if h1 else None
#location
    loc = soup.select_one("div[aria-label='Location']")
    d["location"] = loc.get_text(strip=True) if loc else None
#area
    area = soup.select_one("span[aria-label='Area']")
    d["area"] = area.get_text(strip=True) if area else None
#beds & baths
    beds  = soup.select_one("span[aria-label='Beds']")
    baths = soup.select_one("span[aria-label='Baths']")
    d["bedrooms"]  = beds.get_text(strip=True)  if beds  else None
    d["bathrooms"] = baths.get_text(strip=True) if baths else None

    d["property_type"] = None
    for kw in ["House", "Flat", "Apartment", "Farm House", "Penthouse", "Lower Portion", "Upper Portion"]:
        if d["title"] and kw.lower() in d["title"].lower():
            d["property_type"] = kw
            break
    if not d["property_type"]:
        # Try the canonical URL segment
        m = re.search(r'zameen\.com/([^/]+)/', url)
        if m:
            d["property_type"] = m.group(1).replace("_", " ").title()

    feature_keys = {
        "built_in_year":      ["Built Year", "Year Built", "Year of Construction"],
        "parking_spaces":     ["Parking Spaces", "Car Parking", "Parking"],
        "servant_quarters":   ["Servant Quarters"],
        "store_rooms":        ["Store Rooms", "Store Room"],
        "kitchens":           ["Kitchens", "Kitchen"],
        "drawing_rooms":      ["Drawing Room", "Drawing Rooms"],
        "dining_rooms":       ["Dining Room", "Dining Rooms"],
        "laundry_rooms":      ["Laundry Room"],
        "floors":             ["Floors", "No. of Floors", "Number of Floors"],
        "electricity_backup": ["Electricity Backup", "Backup Electricity"],
        "internet":           ["Internet"],
        "gas":                ["Gas"],
        "security":           ["Security"],
        "water_supply":       ["Water Supply"],
    }
    for k in feature_keys:
        d[k] = None

    all_spans = soup.find_all("span")
    for i, span in enumerate(all_spans):
        label = span.get_text(strip=True)
        for key, labels in feature_keys.items():
            if d[key]:
                continue
            if any(label.lower() == lbl.lower() for lbl in labels):
                if i + 1 < len(all_spans):
                    val = all_spans[i + 1].get_text(strip=True)
                    # Reject if the next span is itself another label
                    if val and not any(val.lower() == lbl.lower()
                                       for lls in feature_keys.values() for lbl in lls):
                        d[key] = val

    
    for row in soup.select("li, tr"):
        cells = [c.get_text(strip=True) for c in row.select("td, span") if c.get_text(strip=True)]
        if len(cells) < 2:
            continue
        label, value = cells[0], cells[1]
        for key, labels in feature_keys.items():
            if d[key]:
                continue
            if any(label.lower() == lbl.lower() for lbl in labels):
                d[key] = value

    return d

def save(records, path):
    if not records:
        return
    pd.DataFrame(records).to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  {len(records)} rows => {path}")

def scrape(target=TARGET):
    driver = setup_driver()
    all_data, seen, page = [], set(), 1

    print(f"\nTarget: {target} listings\n")
    try:
        while len(all_data) < target and page <= 25:
            url = BASE_URL.format(page)
            print(f"\n[Page {page}] {url}")
            urls = get_listing_urls(driver, url)
            new  = [u for u in urls if u not in seen]
            seen.update(new)
            print(f"  => {len(new)} new URLs  |  collected so far: {len(all_data)}")

            if not new:
                print("  No new listings. Stopping.")
                break

            for u in new:
                if len(all_data) >= target:
                    break
                print(f"  [{len(all_data)+1}/{target}] {u[:70]}...")
                rec = parse_detail(driver, u)
                if rec:
                    all_data.append(rec)
                if len(all_data) % 25 == 0:
                    save(all_data, OUTPUT_FILE)
                time.sleep(random.uniform(2.0, 4.0))

            page += 1
            time.sleep(random.uniform(3.0, 6.0))

    except KeyboardInterrupt:
        print("\n[!] Interrupted - saving progress...")
    finally:
        driver.quit()

    save(all_data, OUTPUT_FILE)
    print(f"\nDone! {len(all_data)} listings => '{OUTPUT_FILE}'")

if __name__ == "__main__":
    scrape()