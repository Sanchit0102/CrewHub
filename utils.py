import re
import json
import smtplib
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config
import threading
import time


def send_sms_async(mobile_number, message):
    """
    Send SMS asynchronously in a background thread to avoid blocking the request.
    """
    def send_in_background():
        time.sleep(1)  # Small delay to ensure request completes
        send_sms_message(mobile_number, message)
    
    thread = threading.Thread(target=send_in_background, daemon=True)
    thread.start()


def send_email_async(to_email, worker_name, status, remark=None):
    """
    Send verification email asynchronously in a background thread.
    """
    def send_in_background():
        time.sleep(1)
        send_verification_email(to_email, worker_name, status, remark)
    
    thread = threading.Thread(target=send_in_background, daemon=True)
    thread.start()


def send_appointment_notification_async(to_email, user_name, worker_name, service_type, appointment_date, appointment_time, status, platform_url):
    """
    Send appointment notification email asynchronously in a background thread.
    """
    def send_in_background():
        time.sleep(1)
        send_appointment_notification(to_email, user_name, worker_name, service_type, appointment_date, appointment_time, status, platform_url)
    
    thread = threading.Thread(target=send_in_background, daemon=True)
    thread.start()

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
        with urllib.request.urlopen(req, timeout=8) as response:
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
            # Use Gmail SMTP server with shorter timeout for Vercel
            server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
            server.starttls(timeout=10)
            server.login(sender_email, app_password)
            server.send_message(msg)
            server.quit()
            print(f"[SUCCESS] Verification email successfully sent to {to_email}")
        except smtplib.SMTPAuthenticationError as e:
            print(f"[ERROR] SMTP Authentication failed for {sender_email}. Check MAIL_USERNAME and MAIL_PASSWORD in Vercel environment variables. Error: {str(e)}")
        except smtplib.SMTPException as e:
            print(f"[ERROR] SMTP error sending email. Error: {str(e)}")
        except Exception as e:
            print(f"[ERROR] Failed to send email via SMTP. Error: {str(e)}")


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
    
    msg['From'] = sender_email
    msg['To'] = to_email
    msg['Subject'] = subject
    
    # Create plain text fallback
    text_fallback = f"{title}\n\n{text_content}\n\nAppointment Details:\n- Service: {service_type}\n- Worker: {worker_name}\n- Date: {appointment_date}\n- Time: {appointment_time}\n\n{status_message}\n\nView Dashboard: {platform_url}/dashboard\n\nSupport: support.crewhub@gmail.com"
    
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
            # Use Gmail SMTP server with shorter timeout for Vercel
            server = smtplib.SMTP('smtp.gmail.com', 587, timeout=10)
            server.starttls(timeout=10)
            server.login(sender_email, app_password)
            server.send_message(msg)
            server.quit()
            print(f"[SUCCESS] Appointment notification email successfully sent to {to_email}")
        except smtplib.SMTPAuthenticationError as e:
            print(f"[ERROR] SMTP Authentication failed for {sender_email}. Check MAIL_USERNAME and MAIL_PASSWORD in Vercel environment variables. Error: {str(e)}")
        except smtplib.SMTPException as e:
            print(f"[ERROR] SMTP error sending appointment email. Error: {str(e)}")
        except Exception as e:
            print(f"[ERROR] Failed to send appointment notification email. Error: {str(e)}")
