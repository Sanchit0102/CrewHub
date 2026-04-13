import os
from datetime import timedelta

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    MONGO_URI = os.environ.get('MONGO_URI') or 'mongodb+srv://database2:database2@cluster0.p4ztr4z.mongodb.net/?appName=Cluster0'
    MONGO_DB_NAME = 'crewhub_db'
    
    CLOUDINARY_URL = os.environ.get('CLOUDINARY_URL') or 'cloudinary://557494597539112:zaaMyyIlJboxW6Ca0_mDFxXi56k@decubga08'

    # Razorpay test credentials for demo/development only
    RAZORPAY_KEY_ID = os.environ.get('RAZORPAY_KEY_ID') or 'rzp_test_Scg7T8ulVIgXBA'
    RAZORPAY_KEY_SECRET = os.environ.get('RAZORPAY_KEY_SECRET') or 'jZyIrEYjvskRtpITKANLdSm5'
    RAZORPAY_CURRENCY = 'INR'

    WITHDRAWAL_DATES = [5, 15, 25] 
    PLATFORM_FEE_PERCENTAGE = 15

    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    ADMIN_USERNAME = 'admin@crewhub.org'
    ADMIN_PASSWORD = 'admin123'  

    MAIL_USERNAME = os.environ.get('MAIL_USERNAME', 'support.crewhub@gmail.com')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD', 'eahbsppwpavvecwo')

    SMS_GATEWAY_BASE_URL = os.environ.get('SMS_GATEWAY_BASE_URL', 'https://ds-sms-gateway.vercel.app/api/send')
    SMS_GATEWAY_AUTH = os.environ.get('SMS_GATEWAY_AUTH', 'sanchit')
    PLATFORM_URL = os.environ.get('PLATFORM_URL', 'https://thecrewhub.vercel.app')
    
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads', 'documents')
        
    WORKER_TYPES = [
        'Electrician',
        'Plumber',
        'Carpenter',
        'Painter',
        'Mason',
        'Welder',
        'Gardener',
        'House Cleaning',
        'Pest Control',
        'AC Repair',
        'Other'
    ]
    