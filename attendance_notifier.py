from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import os
import time
import requests
from dotenv import load_dotenv
import json
from datetime import datetime

load_dotenv()

USERNAME = os.getenv("ERP_USERNAME")
PASSWORD = os.getenv("ERP_PASSWORD")
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

STORED_ATTENDANCE_FILE = "stored_attendance.json"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def parse_attendance_table(html):
    """Extract attendance exactly as shown in webpage"""
    soup = BeautifulSoup(html, 'html.parser')
    attendance_data = []
    overall_percentage = "0%"
    
    # Extract overall percentage
    overall_label = soup.find(string="Overall(%) :")
    if overall_label:
        overall_elem = overall_label.find_next()
        if overall_elem:
            overall_text = overall_elem.get_text(strip=True)
            overall_percentage = overall_text
    
    # Find main attendance table
    tables = soup.find_all('table')
    if tables:
        table = tables[0]
        rows = table.find_all('tr')
        
        for row in rows[1:]:  # Skip header
            cols = row.find_all('td')
            if len(cols) >= 5:
                try:
                    sno = cols[0].get_text(strip=True)
                    subject = cols[1].get_text(strip=True)
                    held_text = cols[2].get_text(strip=True)
                    present_text = cols[3].get_text(strip=True)
                    percentage = cols[4].get_text(strip=True)
                    
                    # Skip if empty or month row
                    if not subject or subject.lower() == 'month':
                        continue
                    
                    # Safely convert to integers
                    held = int(held_text) if held_text.isdigit() else 0
                    present = int(present_text) if present_text.isdigit() else 0
                    
                    attendance_data.append({
                        'sno': sno,
                        'subject': subject,
                        'held': held,
                        'present': present,
                        'percentage': percentage
                    })
                except Exception as e:
                    print(f"Error parsing row: {e}")
                    continue
    
    return attendance_data, overall_percentage

def load_stored_attendance():
    """Load previously stored attendance from temp file"""
    if os.path.exists(STORED_ATTENDANCE_FILE):
        try:
            with open(STORED_ATTENDANCE_FILE, 'r') as f:
                data = json.load(f)
                # Ensure it's a dictionary with proper structure
                if isinstance(data, dict) and 'subjects' in data:
                    return data.get('subjects', [])
                elif isinstance(data, list):
                    return data
                else:
                    return None
        except Exception as e:
            print(f"Error loading stored data: {e}")
            return None
    return None

def save_current_attendance(attendance_list, overall_percent):
    """Save current attendance as temporary storage"""
    data = {
        'subjects': attendance_list,
        'overall_percentage': overall_percent,
        'timestamp': datetime.now().strftime("%d/%m/%Y %H:%M")
    }
    with open(STORED_ATTENDANCE_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"✅ Stored {len(attendance_list)} subjects in temporary variables")

def compare_attendance(current, stored):
    """Compare current with stored attendance to find absences"""
    absences = []
    
    if not stored:
        return absences
    
    for curr_subject in current:
        subject_name = curr_subject['subject']
        
        # Find matching subject in stored data
        stored_subject = None
        for stored_subj in stored:
            if stored_subj.get('subject') == subject_name:
                stored_subject = stored_subj
                break
        
        if stored_subject:
            stored_held = stored_subject.get('held', 0)
            stored_present = stored_subject.get('present', 0)
            curr_held = curr_subject['held']
            curr_present = curr_subject['present']
            
            # Check if present count decreased (marked as absent)
            if curr_present < stored_present:
                absences.append({
                    'subject': subject_name,
                    'before_held': stored_held,
                    'before_present': stored_present,
                    'now_held': curr_held,
                    'now_present': curr_present,
                    'classes_missed': stored_present - curr_present
                })
            # Check if held increased but present didn't increase proportionally
            elif curr_held > stored_held and curr_present == stored_present:
                absences.append({
                    'subject': subject_name,
                    'before_held': stored_held,
                    'before_present': stored_present,
                    'now_held': curr_held,
                    'now_present': curr_present,
                    'classes_missed': curr_held - stored_held
                })
    
    return absences

def main():
    print("🚀 LBRCE ATTENDANCE BOT - TEMP VARIABLE STORAGE")
    driver = setup_driver()
    
    try:
        # 1. LOGIN
        print("🔐 Logging in...")
        driver.get("https://erp.lbrce.ac.in/Login/")
        time.sleep(3)
        
        driver.find_element(By.NAME, "txtusername").send_keys(USERNAME)
        driver.find_element(By.NAME, "txtpassword").send_keys(PASSWORD)
        
        login_btn = driver.find_element(By.CSS_SELECTOR, 'button.btn.blue.pull-right[onclick*="login()"]')
        login_btn.click()
        print("✅ Logged in")
        time.sleep(6)
        
        # 2. ATTENDANCE PAGE
        print("📂 Fetching attendance...")
        driver.get("https://erp.lbrce.ac.in/Discipline/StudentHistory.aspx")
        time.sleep(5)
        
        att_btn = driver.find_element(By.NAME, "ctl00$ContentPlaceHolder1$btnAtt")
        att_btn.click()
        print("✅ Attendance loaded")
        time.sleep(6)
        
        # 3. Parse current attendance EXACTLY as in webpage
        html = driver.page_source
        current_attendance, overall_percentage = parse_attendance_table(html)
        
        print(f"✅ Found {len(current_attendance)} subjects")
        print(f"📊 Overall: {overall_percentage}")
        
        # 4. Load previously stored attendance
        stored_attendance = load_stored_attendance()
        
        # 5. Build message
        now = datetime.now().strftime("%d/%m/%Y %H:%M")
        message = f"📊 *ATTENDANCE REPORT*\n"
        message += f"🕐 {now}\n"
        message += f"👤 Roll: `{USERNAME}`\n"
        message += f"📈 Overall: *{overall_percentage}*\n"
        message += "=" * 50 + "\n\n"
        
        # DISPLAY CURRENT ATTENDANCE IN CLEAN FORMAT
        message += "📋 *SUBJECT-WISE ATTENDANCE:*\n\n"
        
        for subject in current_attendance:
            held = subject['held']
            present = subject['present']
            percentage = subject['percentage']
            subject_name = subject['subject']
            
            # Format: Subject | Held | Present | %
            message += f"• *{subject_name}*\n"
            message += f"  Classes: {present}/{held} | Attendance: {percentage}\n\n"
        
        message += "=" * 50 + "\n\n"
        
        # IF STORED DATA EXISTS, COMPARE AND SHOW CHANGES
        if stored_attendance:
            print("📊 Comparing with stored data...")
            absences = compare_attendance(current_attendance, stored_attendance)
            
            if absences:
                message += "🚨 *ABSENCES DETECTED:*\n\n"
                for absence in absences:
                    message += (f"⚠️ *{absence['subject']}*\n"
                               f"   Before: {absence['before_present']}/{absence['before_held']} classes\n"
                               f"   Now: {absence['now_present']}/{absence['now_held']} classes\n"
                               f"   🔴 *MISSED: {absence['classes_missed']} class(es)*\n\n")
            else:
                message += "✅ *NO ABSENCES* - Attendance unchanged from last check\n"
        else:
            message += ("ℹ️ *FIRST CHECK*\n"
                       "Data stored! Run tomorrow to detect absences.\n")
        
        # Send to Telegram
        resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
            'chat_id': CHAT_ID,
            'text': message,
            'parse_mode': 'Markdown'
        })
        
        print(f"📱 Telegram: {resp.status_code}")
        
        # 6. SAVE CURRENT AS STORED FOR NEXT COMPARISON
        save_current_attendance(current_attendance, overall_percentage)
        
        # Save screenshot
        driver.save_screenshot("attendance_current.png")
        print("📸 Screenshot saved")
        
        print("🎉 Done! Check Telegram!")
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        error_msg = f"❌ *Bot Error*\n\n{str(e)}"
        try:
            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={
                'chat_id': CHAT_ID,
                'text': error_msg
            })
        except:
            pass
    finally:
        input("Press Enter to close browser...")
        driver.quit()

if __name__ == "__main__":
    main()
