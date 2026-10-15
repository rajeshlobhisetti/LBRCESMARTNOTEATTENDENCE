import logging
import os
import shutil
import threading
import time
import gc
from typing import Tuple, List, Dict, Any, Optional
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.config import settings

logger = logging.getLogger(__name__)

# Concurrency lock: Ensure only 1 Chrome instance ever runs at a time in low-memory container
SCRAPE_SEMAPHORE = threading.Semaphore(1)

def get_chrome_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--no-zygote")
    options.add_argument("--single-process")
    options.add_argument("--window-size=1280,720")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-default-apps")
    options.add_argument("--disable-sync")
    options.add_argument("--disable-translate")
    options.add_argument("--metrics-recording-only")
    options.add_argument("--mute-audio")
    options.add_argument("--no-first-run")
    options.add_argument("--safebrowsing-disable-auto-update")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--disk-cache-size=1")
    options.add_argument("--media-cache-size=1")
    options.add_argument("--js-flags=--max-old-space-size=128")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # Detect linux chromium or google-chrome binary if present
    for bin_path in [
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome"
    ]:
        if bin_path and os.path.exists(bin_path):
            options.binary_location = bin_path
            break

    # Detect chromedriver service if present
    service = None
    for driver_path in [
        shutil.which("chromedriver"),
        "/usr/bin/chromedriver",
        "/usr/lib/chromium/chromedriver"
    ]:
        if driver_path and os.path.exists(driver_path):
            service = Service(executable_path=driver_path)
            break

    if service:
        return webdriver.Chrome(service=service, options=options)
    return webdriver.Chrome(options=options)

def parse_attendance_html(html: str) -> Tuple[List[Dict[str, Any]], str]:
    """
    Parses the student history HTML and extracts overall percentage and subjects table.
    """
    soup = BeautifulSoup(html, "html.parser")
    attendance_data = []
    overall_percentage = "N/A"

    # Extract overall percentage
    overall_label = soup.find(string=lambda t: t and "Overall(%) :" in t)
    if overall_label:
        parent = overall_label.find_next()
        if parent:
            overall_percentage = parent.get_text(strip=True)

    # Find attendance table
    tables = soup.find_all("table")
    if tables:
        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue

            for row in rows:
                cols = row.find_all("td")
                if len(cols) >= 5:
                    try:
                        sno = cols[0].get_text(strip=True)
                        subject = cols[1].get_text(strip=True)
                        held_text = cols[2].get_text(strip=True)
                        present_text = cols[3].get_text(strip=True)
                        percentage = cols[4].get_text(strip=True)

                        # Skip header or month rows
                        if not subject or subject.lower() in ["subject", "month", "sno", "s.no"]:
                            continue

                        held = int(held_text) if held_text.isdigit() else 0
                        present = int(present_text) if present_text.isdigit() else 0

                        attendance_data.append({
                            "sno": sno,
                            "subject": subject,
                            "held": held,
                            "present": present,
                            "percentage": percentage
                        })
                    except Exception as e:
                        logger.debug(f"Error parsing attendance row: {e}")
                        continue
            if attendance_data:
                break

    return attendance_data, overall_percentage

def compare_attendance_records(
    current: List[Dict[str, Any]],
    previous: Optional[List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    Compares current attendance with previously stored attendance to identify newly missed classes.
    """
    absences = []
    if not previous:
        return absences

    for curr in current:
        subj_name = curr.get("subject")
        prev = next((p for p in previous if p.get("subject") == subj_name), None)

        if prev:
            prev_held = prev.get("held", 0)
            prev_present = prev.get("present", 0)
            curr_held = curr.get("held", 0)
            curr_present = curr.get("present", 0)

            held_diff = curr_held - prev_held
            present_diff = curr_present - prev_present

            # Case 1: More classes were conducted than attended (Absence occurred)
            if held_diff > 0 and held_diff > present_diff:
                missed = held_diff - max(0, present_diff)
                absences.append({
                    "subject": subj_name,
                    "before_held": prev_held,
                    "before_present": prev_present,
                    "now_held": curr_held,
                    "now_present": curr_present,
                    "classes_missed": missed
                })
            # Case 2: Present count decreased (marked absent after retrospective correction)
            elif curr_present < prev_present:
                absences.append({
                    "subject": subj_name,
                    "before_held": prev_held,
                    "before_present": prev_present,
                    "now_held": curr_held,
                    "now_present": curr_present,
                    "classes_missed": prev_present - curr_present
                })

    return absences

def scrape_student_attendance(
    roll_no: str,
    erp_password: str,
    previous_attendance: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """
    Logs into LBRCE ERP with roll_no & erp_password, navigates to StudentHistory.aspx,
    retrieves current attendance, and compares against previous attendance.
    Guarded by SCRAPE_SEMAPHORE to ensure only 1 Chrome instance runs at a time.
    """
    with SCRAPE_SEMAPHORE:
        driver = None
        try:
            driver = get_chrome_driver()
            login_url = f"{settings.ERP_BASE_URL.rstrip('/')}/Login/"

            logger.info(f"Navigating to login page for student {roll_no}")
            driver.get(login_url)
            time.sleep(2)

            # Enter credentials
            user_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "txtusername"))
            )
            pass_input = driver.find_element(By.NAME, "txtpassword")

            user_input.clear()
            user_input.send_keys(roll_no)
            pass_input.clear()
            pass_input.send_keys(erp_password)

            # Click login button
            login_btn = driver.find_element(
                By.CSS_SELECTOR, 'button.btn.blue.pull-right[onclick*="login()"]'
            )
            login_btn.click()
            time.sleep(4)

            # Check for error in login or failure to redirect from /Login/
            time.sleep(2)
            body_text = driver.find_element(By.TAG_NAME, "body").text
            if "error" in body_text.lower() or "please check user name" in body_text.lower() or "/login" in driver.current_url.lower():
                logger.warning(f"Invalid ERP credentials for roll number {roll_no}")
                return {
                    "success": False,
                    "error": "Invalid ERP Roll Number or Password. LBRCE ERP rejected the login.",
                    "overall_percentage": "N/A",
                    "subjects": [],
                    "absences": []
                }

            # Navigate to attendance page
            history_url = f"{settings.ERP_BASE_URL.rstrip('/')}/Discipline/StudentHistory.aspx"
            logger.info(f"Navigating to StudentHistory for {roll_no}")
            driver.get(history_url)
            time.sleep(3)

            # Click attendance button
            try:
                att_btn = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.NAME, "ctl00$ContentPlaceHolder1$btnAtt"))
                )
                att_btn.click()
                time.sleep(4)
            except Exception as e:
                logger.error(f"Could not click attendance button for {roll_no}: {e}")
                return {
                    "success": False,
                    "error": "Failed to load attendance view from ERP. Button not found or session expired.",
                    "overall_percentage": "N/A",
                    "subjects": [],
                    "absences": []
                }

            # Parse table
            subjects, overall_percentage = parse_attendance_html(driver.page_source)

            if not subjects:
                return {
                    "success": False,
                    "error": "Attendance data table not found in ERP response.",
                    "overall_percentage": overall_percentage,
                    "subjects": [],
                    "absences": []
                }

            # Compare with previous
            absences = compare_attendance_records(subjects, previous_attendance)

            logger.info(f"Successfully scraped attendance for {roll_no}: {overall_percentage}, {len(subjects)} subjects")
            return {
                "success": True,
                "error": None,
                "overall_percentage": overall_percentage,
                "subjects": subjects,
                "absences": absences
            }

        except Exception as e:
            logger.error(f"Scraper exception for {roll_no}: {e}")
            return {
                "success": False,
                "error": str(e),
                "overall_percentage": "N/A",
                "subjects": [],
                "absences": []
            }
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            gc.collect()

def verify_credentials_quick(roll_no: str, erp_password: str) -> Tuple[bool, str]:
    """
    Quickly verifies if roll_no and password are valid on LBRCE ERP using direct HTTP request.
    Ultra-fast (under 500ms) with zero Chrome memory usage.
    """
    try:
        session = requests.Session()
        session.verify = False
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        login_page_url = f"{settings.ERP_BASE_URL.rstrip('/')}/Login/"
        session.get(login_page_url, timeout=10)

        login_api_url = f"{settings.ERP_BASE_URL.rstrip('/')}/Login/default.aspx/Login"
        resp = session.post(
            login_api_url,
            json={"UserID": roll_no.strip(), "PWD": erp_password.strip()},
            headers={"Content-Type": "application/json; charset=UTF-8"},
            timeout=10
        )
        data = resp.json()
        val = str(data.get("d", "")).strip()

        if val in ["1", "2"] or val.endswith("dbs"):
            return True, "Credentials verified successfully!"
        elif "check" in val.lower() or "error" in val.lower():
            return False, "Invalid Roll Number or ERP Password. LBRCE ERP rejected credentials."
        else:
            return False, f"LBRCE ERP returned: {val}"
    except Exception as http_err:
        logger.warning(f"Fast verification encountered exception: {http_err}. Falling back to browser...")
        return _verify_credentials_with_browser(roll_no, erp_password)

def _verify_credentials_with_browser(roll_no: str, erp_password: str) -> Tuple[bool, str]:
    with SCRAPE_SEMAPHORE:
        driver = None
        try:
            driver = get_chrome_driver()
            login_url = f"{settings.ERP_BASE_URL.rstrip('/')}/Login/"
            driver.get(login_url)
            time.sleep(2)

            user_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.NAME, "txtusername"))
            )
            pass_input = driver.find_element(By.NAME, "txtpassword")

            user_input.clear()
            user_input.send_keys(roll_no)
            pass_input.clear()
            pass_input.send_keys(erp_password)

            login_btn = driver.find_element(
                By.CSS_SELECTOR, 'button.btn.blue.pull-right[onclick*="login()"]'
            )
            login_btn.click()
            time.sleep(3)
            body = driver.find_element(By.TAG_NAME, "body").text
            if "error" in body.lower() or "please check" in body.lower() or "/login" in driver.current_url.lower():
                return False, "Invalid Roll Number or ERP Password. LBRCE ERP rejected credentials."

            return True, "Credentials verified successfully!"
        except Exception as e:
            return False, f"Verification failed: {str(e)}"
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
            gc.collect()

