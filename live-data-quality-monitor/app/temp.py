import smtplib

EMAIL_ADDRESS = "prajwalshevante1@gmail.com"
EMAIL_PASSWORD = "yanm efov lsfk tnku"

try:
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    print("SUCCESS — credentials work")
    server.quit()
except Exception as e:
    print("FAILED:", e)