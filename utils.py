import re
import json
import smtplib
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config

# A dummy implementation that just logs to console (useful before proper SMTP is setup)
# Alternatively, it uses config values if provided.
def send_sms_message(mobile_number, message):
    """
    Send a plain text SMS via the configured SMS gateway.
    """
    if not mobile_number or not message:
        return False

    numeric = re.sub(r'\D', '', str(mobile_number))
    if len(numeric) == 10:
        numeric = '91' + numeric
    elif len(numeric) == 12 and numeric.startswith('91'):
        pass
    elif len(numeric) > 12:
        numeric = '91' + numeric[-10:]
    else:
        return False

    to_number = f'+{numeric}'
    payload = json.dumps({'to': to_number, 'message': message}).encode('utf-8')
    url = f"{Config.SMS_GATEWAY_BASE_URL}?auth={Config.SMS_GATEWAY_AUTH}"

    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            status_code = response.getcode()
            response_body = response.read().decode('utf-8', errors='ignore')
            print(f"[SMS] Sent to {to_number}. Status: {status_code}. Response: {response_body}")
            return status_code == 200
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore') if hasattr(e, 'read') else ''
        print(f"[SMS ERROR] HTTP {e.code} for {to_number}: {error_body}")
    except Exception as e:
        print(f"[SMS ERROR] Failed to send SMS to {to_number}: {str(e)}")
    return False


def send_verification_email(to_email, worker_name, status, remark=None):
    """
    Sends an email to the worker regarding their verification status.
    """
    subject = f"CrewHub Verification Status: {status.upper()}"
    
    if status == 'approved':
        header_color = "#059669" # Green
        title = "Account Approved"
        text_content = f"Congratulations {worker_name}! Your CrewHub worker account has been successfully verified and approved."
        action_html = f"""
            <div style="text-align: center; margin: 30px 0;">
                <a href="{Config.PLATFORM_URL}/login" style="background-color: #4F46E5; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Login to CrewHub</a>
            </div>
            <p style="text-align: center; font-size: 13px; color: #6b7280;">Or copy this link: <a href="{Config.PLATFORM_URL}/login" style="color: #4F46E5;">{Config.PLATFORM_URL}/login</a></p>
        """
    else:
        header_color = "#DC2626" # Red
        title = "Account Rejected"
        text_content = f"Hello {worker_name}, unfortunately your CrewHub worker application was rejected."
        action_html = f"""
            <div style="background-color: #FEF2F2; border-left: 4px solid #DC2626; padding: 16px; margin: 20px 0; border-radius: 4px;">
                <p style="margin: 0; color: #991B1B; font-weight: bold;">Reason for Rejection:</p>
                <p style="margin: 8px 0 0 0; color: #7F1D1D;">{remark}</p>
            </div>
            <p style="color: #4b5563;">Please contact support if you believe this was a mistake or to appeal.</p>
        """

    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; margin: 0; padding: 40px 20px;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
            <!-- Header -->
            <div style="background-color: {header_color}; padding: 30px 20px; text-align: center;">
                <h1 style="color: #ffffff; margin: 0; font-size: 28px; letter-spacing: 1px;">CrewHub</h1>
                <p style="color: rgba(255, 255, 255, 0.8); margin: 5px 0 0 0; font-size: 14px;">Service Marketplace</p>
            </div>
            
            <!-- Body -->
            <div style="padding: 40px 30px;">
                <h2 style="color: #1f2937; margin-top: 0;">{title}</h2>
                <p style="color: #4b5563; font-size: 16px; line-height: 1.5;">
                    {text_content}
                </p>
                
                {action_html}
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb;">
                <p style="color: #9ca3af; font-size: 13px; margin: 0;">
                    Need help? Contact us at <a href="mailto:support@crewhub.in" style="color: #4F46E5; text-decoration: none;">support@crewhub.in</a>
                </p>
                <p style="color: #9ca3af; font-size: 12px; margin: 10px 0 0 0;">
                    &copy; 2026 CrewHub Platform. All rights reserved.
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    
    # Import config to get credentials here to avoid circular imports if any
    from config import Config
    sender_email = Config.MAIL_USERNAME
    app_password = Config.MAIL_PASSWORD
    
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    
    # Create plain text fallback
    text_fallback = f"{title}\n\n{text_content}\n\nSupport: support.crewhub@gmail.com"
    
    # Attach parts (HTML goes last as it's preferred)
    msg.attach(MIMEText(text_fallback, 'plain'))
    msg.attach(MIMEText(html_template, 'html'))

    # If the user hasn't set up the password yet, fallback to console print
    if not app_password or app_password == 'your_16_digit_app_password':
        print(f"\n[WARNING] Email not sent to inbox because MAIL_PASSWORD is not configured in config.py.")
        print(f"========== EMAIL SENT (SIMULATED) ==========")
        print(f"TO: {to_email}")
        print(f"SUBJECT: {subject}")
        print(f"BODY:\n{text_fallback}")
        print(f"============================================\n")
    else:
        try:
            # Use Gmail SMTP server
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(sender_email, app_password)
            server.send_message(msg)
            server.quit()
            print(f"[SUCCESS] Verification email successfully sent to {to_email}")
        except Exception as e:
            print(f"[ERROR] Failed to send email via SMTP. Ensure your App Password is correct. Error: {str(e)}")
