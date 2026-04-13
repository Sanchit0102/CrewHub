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
    try:
        if not mobile_number or not message:
            print(f"[SMS] Skipped: missing mobile or message")
            return False

        numeric = re.sub(r'\D', '', str(mobile_number))
        if len(numeric) == 10:
            numeric = '91' + numeric
        elif len(numeric) == 12 and numeric.startswith('91'):
            pass
        elif len(numeric) > 12:
            numeric = '91' + numeric[-10:]
        else:
            print(f"[SMS] Invalid phone number format: {mobile_number}")
            return False

        to_number = f'+{numeric}'
        # Correct payload format for SMS gateway (auth goes in URL, not payload)
        payload = json.dumps({
            'to': to_number, 
            'message': message
        }).encode('utf-8')
        # Auth parameter goes in URL query string
        url = f"{Config.SMS_GATEWAY_BASE_URL}?auth={Config.SMS_GATEWAY_AUTH}"

        print(f"[SMS] Sending to URL: {url}")
        print(f"[SMS] Payload: {payload.decode('utf-8', errors='ignore')[:100]}...")
        
        req = urllib.request.Request(url, data=payload, headers={
            'Content-Type': 'application/json',
            'User-Agent': 'CrewHub/1.0'
        })
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.getcode()
            response_body = response.read().decode('utf-8', errors='ignore')
            print(f"[SMS SUCCESS] Sent to {to_number}. Status: {status_code}, Response: {response_body[:100]}")
            return status_code == 200
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='ignore') if e.fp else 'No response body'
        print(f"[SMS ERROR] HTTP {e.code} to SMS gateway: {e.reason}")
        print(f"[SMS ERROR] Response body: {error_body[:200]}")
        return False
    except urllib.error.URLError as e:
        print(f"[SMS ERROR] Network error: {str(e)}")
        return False
    except Exception as e:
        print(f"[SMS ERROR] Failed: {str(e)}")
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
    
    print(f"[Email] Attempting to send to {to_email} from {sender_email}")
    
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    
    # Create plain text fallback
    text_fallback = f"{title}\n\n{text_content}\n\nSupport: support.crewhub@gmail.com"
    
    # Attach parts (HTML goes last as it's preferred)
    msg.attach(MIMEText(text_fallback, 'plain'))
    msg.attach(MIMEText(html_template, 'html'))

    # If the user hasn't set up the password yet, fallback to console print
    if not app_password or app_password == 'your_16_digit_app_password' or app_password == 'eahbsppwpavvecwo':
        print(f"[Email WARNING] Credentials not configured. Skipping email to {to_email}")
        return False
    
    try:
        # Use Gmail SMTP server with short timeout
        print(f"[Email] Connecting to Gmail SMTP...")
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=8)
        server.starttls()
        print(f"[Email] Logging in as {sender_email}...")
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print(f"[Email SUCCESS] Verification email sent to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"[Email ERROR] Authentication failed for {sender_email}. Check MAIL_USERNAME and MAIL_PASSWORD environment variables on Vercel.")
        return False
    except smtplib.SMTPException as e:
        print(f"[Email ERROR] SMTP error: {str(e)}")
        return False
    except Exception as e:
        print(f"[Email ERROR] Failed to send: {str(e)}")
        return False


def send_appointment_notification(to_email, user_name, worker_name, service_type, appointment_date, appointment_time, status, platform_url):
    """
    Sends an email to the user regarding their appointment status (accepted/rejected).
    """
    subject = f"CrewHub Appointment {status.capitalize()}"
    
    if status == 'accepted':
        header_color = "#059669"  # Green
        title = "Appointment Confirmed"
        text_content = f"Great news {user_name}! Your appointment with {worker_name} has been accepted."
        status_icon = "✅"
        status_message = "Your appointment has been confirmed and is scheduled."
    else:
        header_color = "#DC2626"  # Red
        title = "Appointment Declined"
        text_content = f"Hello {user_name}, unfortunately your appointment with {worker_name} has been declined."
        status_icon = "❌"
        status_message = "Your appointment request has been declined by the worker."
    
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
                <h2 style="color: #1f2937; margin-top: 0; text-align: center;">{status_icon} {title}</h2>
                
                <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 20px 0;">
                    <p style="color: #4b5563; font-size: 16px; line-height: 1.5; margin: 0 0 20px 0;">
                        {text_content}
                    </p>
                    
                    <div style="background-color: #ffffff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 16px; margin: 16px 0;">
                        <h3 style="color: #1f2937; margin: 0 0 12px 0; font-size: 16px;">Appointment Details</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #6b7280; font-weight: 500; width: 120px;">Service:</td>
                                <td style="padding: 8px 0; color: #1f2937; font-weight: 600;">{service_type}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6b7280; font-weight: 500;">Worker:</td>
                                <td style="padding: 8px 0; color: #1f2937; font-weight: 600;">{worker_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6b7280; font-weight: 500;">Date:</td>
                                <td style="padding: 8px 0; color: #1f2937; font-weight: 600;">{appointment_date}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #6b7280; font-weight: 500;">Time:</td>
                                <td style="padding: 8px 0; color: #1f2937; font-weight: 600;">{appointment_time}</td>
                            </tr>
                        </table>
                    </div>
                    
                    <div style="background-color: {header_color}; color: #ffffff; padding: 16px; border-radius: 6px; text-align: center; margin: 20px 0;">
                        <strong>{status_message}</strong>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{platform_url}/dashboard" style="background-color: #4F46E5; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">View Dashboard</a>
                </div>
                <p style="text-align: center; font-size: 13px; color: #6b7280;">Or copy this link: <a href="{platform_url}/dashboard" style="color: #4F46E5;">{platform_url}/dashboard</a></p>
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
    
    print(f"[Appointment Email] Attempting to send to {to_email}")
    
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    
    # Create plain text fallback
    text_fallback = f"{title}\n\n{text_content}\n\nAppointment Details:\n- Service: {service_type}\n- Worker: {worker_name}\n- Date: {appointment_date}\n- Time: {appointment_time}\n\n{status_message}\n\nView Dashboard: {platform_url}/dashboard\n\nSupport: support.crewhub@gmail.com"
    
    # Attach parts (HTML goes last as it's preferred)
    msg.attach(MIMEText(text_fallback, 'plain'))
    msg.attach(MIMEText(html_template, 'html'))

    # If the user hasn't set up the password yet, skip
    if not app_password or app_password == 'your_16_digit_app_password':
        print(f"[Appointment Email WARNING] Credentials not configured. Skipping email to {to_email}")
        return False
    
    try:
        # Use Gmail SMTP server with short timeout
        print(f"[Appointment Email] Connecting to Gmail...")
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=8)
        server.starttls()
        print(f"[Appointment Email] Logging in...")
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print(f"[Appointment Email SUCCESS] Sent to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"[Appointment Email ERROR] Authentication failed. Check MAIL_USERNAME and MAIL_PASSWORD environment variables on Vercel.")
        return False
    except smtplib.SMTPException as e:
        print(f"[Appointment Email ERROR] SMTP error: {str(e)}")
        return False
    except Exception as e:
        print(f"[Appointment Email ERROR] Failed to send: {str(e)}")
        return False


def send_reset_password_email(to_email, user_name, otp, expires_minutes=Config().RESET_PASS_OTP_EXPIRY_MINUTES):
    """
    Send password reset OTP email.
    """
    subject = 'CrewHub Password Reset OTP'
    html_template = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset=\"utf-8\">
        <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    </head>
    <body style=\"font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #f3f4f6; margin: 0; padding: 40px 20px;\">
        <div style=\"max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);\">
            <div style=\"background-color: #4F46E5; padding: 30px 20px; text-align: center;\">
                <h1 style=\"color: #ffffff; margin: 0; font-size: 28px; letter-spacing: 1px;\">CrewHub Support</h1>
            </div>
            <div style=\"padding: 40px 30px;\">
                <h2 style=\"color: #1f2937; margin-top: 0;\">Password Reset Request</h2>
                <p style=\"color: #4b5563; font-size: 16px; line-height: 1.5;\">Dear {user_name},</p>
                <p style=\"color: #4b5563; font-size: 16px; line-height: 1.5;\">
                    We received a request to reset the password for your account associated with this email address.
                </p>
                <div style=\"background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 24px; margin: 24px 0; text-align: center;\">
                    <p style=\"color: #6b7280; font-size: 14px; margin-bottom: 10px;\">Your One-Time Password (OTP) is:</p>
                    <p style=\"font-size: 28px; font-weight: 700; margin: 0; letter-spacing: 6px; color: #111827;\">{otp}</p>
                </div>
                <p style=\"color: #4b5563; font-size: 16px; line-height: 1.5;\">This OTP is valid for the next {expires_minutes} minutes. Please do not share this code with anyone for security reasons.</p>
                <p style=\"color: #4b5563; font-size: 16px; line-height: 1.5;\">If you did not request a password reset, please ignore this email or contact our support team immediately.</p>
                <p style=\"color: #4b5563; font-size: 16px; line-height: 1.5;\">Thank you,<br>CrewHub Support Team</p>
            </div>
            <div style=\"background-color: #f9fafb; padding: 20px; text-align: center; border-top: 1px solid #e5e7eb;\">
                <p style=\"color: #9ca3af; font-size: 13px; margin: 0;\">Need help? Contact us at <a href=\"mailto:support@crewhub.in\" style=\"color: #4F46E5; text-decoration: none;\">support@crewhub.in</a></p>
            </div>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart('alternative')
    sender_email = Config.MAIL_USERNAME
    app_password = Config.MAIL_PASSWORD

    if not sender_email or not app_password or app_password == 'your_16_digit_app_password':
        print(f"[Reset Email WARNING] SMTP credentials not configured. Skipping reset OTP email to {to_email}")
        return False

    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(f"Dear {user_name},\n\nYour OTP is: {otp}\nThis OTP is valid for the next {expires_minutes} minutes.\n\nIf you did not request a password reset, please ignore this email.", 'plain'))
    msg.attach(MIMEText(html_template, 'html'))

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587, timeout=8)
        server.starttls()
        server.login(sender_email, app_password)
        server.send_message(msg)
        server.quit()
        print(f"[Reset Email SUCCESS] Sent OTP email to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"[Reset Email ERROR] Authentication failed for {sender_email}. Check MAIL_USERNAME and MAIL_PASSWORD environment variables.")
        return False
    except smtplib.SMTPException as e:
        print(f"[Reset Email ERROR] SMTP error: {str(e)}")
        return False
    except Exception as e:
        print(f"[Reset Email ERROR] Failed to send: {str(e)}")
        return False
