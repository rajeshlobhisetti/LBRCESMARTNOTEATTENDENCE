import logging
import time
from typing import Tuple, List, Dict, Any, Optional
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from app.config import settings

logger = logging.getLogger(__name__)

def get_chrome_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    # Headless arguments for server / docker stability
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-setuid-sandbox")
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
        # The main attendance table is the first or table with headers
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
    """
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
        time.sleep(3)
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

def verify_credentials_quick(roll_no: str, erp_password: str) -> Tuple[bool, str]:
    """
    Quickly verifies if roll_no and password are valid on LBRCE ERP.
    """
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
