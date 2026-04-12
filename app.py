"""
CrewHub - Service Marketplace Platform
Main Flask Application (Controller Layer - MVC Pattern)

Technology Commercialization & Startup Development Project
Scalability: Modular architecture allows easy addition of features like ratings, payments, chat
"""

import os
import uuid
from datetime import datetime
from bson.objectid import ObjectId
from flask import Flask, render_template, request, redirect, url_for, session, flash
from config import Config
from models import Database, User, Worker, Authentication, Appointment, Review, Report, Bill, Withdrawal, AuditLog
from functools import wraps
import re
from werkzeug.utils import secure_filename
from utils import send_verification_email, send_sms_message
import cloudinary
import cloudinary.uploader
import pytz


# Initialize Flask application
app = Flask(__name__)
app.config.from_object(Config)

# Configuration for Cloudinary
cloudinary_url = app.config.get('CLOUDINARY_URL')
if cloudinary_url:
    os.environ["CLOUDINARY_URL"] = cloudinary_url
    try:
        from cloudinary import config as cloudinary_config
        # Clean the URL if it was accidentally malformed
        url = cloudinary_url.replace('CLOUDINARY_URL=', '').strip()
        # Parse components manually for maximum compatibility
        pattern = r"cloudinary://([^:]+):([^@]+)@(.+)"
        match = re.match(pattern, url)
        if match:
            api_key, api_secret, cloud_name = match.groups()
            cloudinary.config(
                cloud_name=cloud_name,
                api_key=api_key,
                api_secret=api_secret,
                secure=True
            )
    except Exception as e:
        print(f"Cloudinary config error: {e}")

# Initialize database connection
db = Database(app.config['MONGO_URI'], app.config['MONGO_DB_NAME']).db

# Initialize models
user_model = User(db)
worker_model = Worker(db)
auth = Authentication(db)
appointment_model = Appointment(db)
review_model = Review(db)
report_model = Report(db)
bill_model = Bill(db)
withdrawal_model = Withdrawal(db)
audit_log = AuditLog(db)


# Decorator for login required
def login_required(f):
    """
    Decorator to protect routes that require authentication
    Security: Ensures only authenticated users can access protected pages
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session and not session.get('admin'):
            flash('Please login to access this page', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Decorator for role-based access
def role_required(allowed_roles):
    """
    Decorator to restrict access based on user role
    Business Logic: Different dashboards and features for different roles
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('Please login to access this page', 'error')
                return redirect(url_for('login'))
            
            if session.get('role') not in allowed_roles:
                flash('You do not have permission to access this page', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


# Decorator for admin access
def admin_required(f):
    """
    Decorator to restrict access to admin
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin'):
            flash('Admin access required', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


# Setup Admin Status Processor
@app.context_processor
def inject_admin_status():
    if session.get('admin'):
        pending_count = len(worker_model.get_pending_workers())
        pending_payouts = len(withdrawal_model.get_pending())
        return {
            'pending_worker_count': pending_count,
            'pending_payout_count': pending_payouts
        }
    return {'pending_worker_count': 0, 'pending_payout_count': 0}

@app.route('/')
def index():
    """
    Home page route
    Shows platform overview and value proposition
    """
    # Get some stats for the homepage
    total_workers = len(worker_model.get_all_active())
    worker_types = worker_model.count_by_type()
    
    return render_template('index.html', 
                         total_workers=total_workers,
                         worker_types=worker_types,
                         logged_in='user_id' in session)


@app.route('/login', methods=['GET', 'POST'])
def login():
    """
    Unified login route for all user types
    Business Logic: Single authentication portal enhances user experience
    """
    # Redirect if already logged in
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Validate inputs
        if not email or not password:
            flash('Please provide both email and password', 'error')
            return render_template('login.html')
        
        # Admin Login (Case-insensitive check)
        expected_user = app.config['ADMIN_USERNAME'].lower()
        if email.lower() == expected_user:
            if password == app.config['ADMIN_PASSWORD']:
                session['admin'] = True
                session['role'] = 'admin'
                session['email'] = email
                flash('Admin login successful!', 'success')
                return redirect(url_for('admin_dashboard'))
            else:
                print(f"DEBUG: Admin email matched ({expected_user}), but password was incorrect.")
        else:
            print(f"DEBUG: Admin email mismatch. Expected: '{expected_user}', Received: '{email.lower()}'")

        # Authenticate user
        user_data, role = auth.authenticate(email, password)
        
        if user_data:
            if role == 'worker':
                status = user_data.get('status', 'approved')
                if status == 'pending':
                    flash('Your request is still under review by the Admin.', 'warning')
                    return redirect(url_for('login'))
                elif status == 'rejected':
                    remark = user_data.get('rejection_remark', 'No reason provided')
                    flash(f'Your registration was rejected. Reason: {remark}', 'error')
                    return redirect(url_for('login'))
                
                # Ban Check
                is_banned = user_data.get('is_banned', False)
                if is_banned:
                    ban_until = user_data.get('ban_until')
                    if ban_until:
                        if datetime.utcnow() > ban_until:
                            # Ban expired, auto-unban
                            worker_model.update_ban_status(user_data['_id'], False)
                        else:
                            # Still banned
                            remaining = ban_until - datetime.utcnow()
                            days = remaining.days
                            hours = remaining.seconds // 3600
                            flash(f'Your account is temporarily suspended. Try again in {days}d {hours}h.', 'error')
                            return redirect(url_for('login'))
                    else:
                        # Permanent Ban
                        flash('Your account has been permanently banned from the platform.', 'error')
                        return redirect(url_for('login'))
                
            # Set session variables
            session['user_id'] = str(user_data['_id'])
            session['role'] = role
            session['email'] = email
            session.pop('admin', None)  # Clear admin flag for regular users
            session.permanent = True
            
            flash(f'Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password', 'error')
    
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Unified registration route with role selection
    UX: Single page for all registrations with dynamic role switching
    """
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        role = request.form.get('role', 'user')
        full_name = request.form.get('full_name', '').strip()
        mobile = request.form.get('mobile', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        pincode = request.form.get('pincode', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Common Validation
        if not all([full_name, mobile, email, address, pincode, password, confirm_password]):
            flash('All fields are required', 'error')
            return render_template('register.html', worker_types=Config.WORKER_TYPES)
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html', worker_types=Config.WORKER_TYPES)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('register.html', worker_types=Config.WORKER_TYPES)
        
        if len(mobile) != 10 or not mobile.isdigit():
            flash('Please enter a valid 10-digit mobile number', 'error')
            return render_template('register.html', worker_types=Config.WORKER_TYPES)
        
        if len(pincode) != 6 or not pincode.isdigit():
            flash('Please enter a valid 6-digit pincode', 'error')
            return render_template('register.html', worker_types=Config.WORKER_TYPES)
        
        if role == 'worker':
            worker_type = request.form.get('worker_type', '').strip()
            if worker_type == 'Other':
                worker_type = request.form.get('other_worker_type', '').strip()
                if not worker_type:
                    worker_type = 'Other (General)'
            available_cities = request.form.get('available_cities', '').strip()
            if not worker_type or not available_cities:
                flash('Worker type and cities are required for workers', 'error')
                return render_template('register.html', worker_types=Config.WORKER_TYPES)
            
            # File Uploads
            aadhar_file = request.files.get('aadhar')
            cert_file = request.files.get('certificate')
            photo_file = request.files.get('profile_photo')
            
            if not aadhar_file or not cert_file or not photo_file or \
               aadhar_file.filename == '' or cert_file.filename == '' or photo_file.filename == '':
                flash('Profile Photo, Aadhar Card and Certificate are required for verification', 'error')
                return render_template('register.html', worker_types=Config.WORKER_TYPES)

            # Upload to Cloudinary instead of local storage
            try:
                # Upload Aadhar
                aadhar_result = cloudinary.uploader.upload(aadhar_file, folder="crewhub/aadhar")
                aadhar_url = aadhar_result['secure_url']
                
                # Upload Certificate
                cert_result = cloudinary.uploader.upload(cert_file, folder="crewhub/certificates")
                cert_url = cert_result['secure_url']
                
                # Upload Profile Photo
                photo_url = None
                if photo_file and photo_file.filename != '':
                    photo_result = cloudinary.uploader.upload(photo_file, folder="crewhub/photos")
                    photo_url = photo_result['secure_url']
                
                worker_id = worker_model.create(full_name, mobile, email, address, pincode, 
                                               worker_type, available_cities, password, aadhar_url, cert_url, photo_url)
            except Exception as e:
                flash(f'Upload failed: {str(e)}', 'error')
                return render_template('register.html', worker_types=Config.WORKER_TYPES)
            if worker_id:
                flash('Registration submitted! Please wait for admin verification.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Email already registered.', 'error')
        else:
            user_id = user_model.create(full_name, mobile, email, address, pincode, password)
            if user_id:
                flash('Registration successful! Please login.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Email already registered.', 'error')
                
    return render_template('register.html', worker_types=Config.WORKER_TYPES)


@app.route('/register/user')
def register_user_redirect():
    return redirect(url_for('register'))


@app.route('/register/worker')
def register_worker_redirect():
    return redirect(url_for('register'))

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    """Admin dashboard for managing the platform"""
    total_users = len(user_model.get_all_users())
    total_workers = len(worker_model.get_all_workers())
    active_workers = len(worker_model.get_all_active())
    banned_workers = db.workers.count_documents({'is_banned': True})
    
    # Get pending reports
    reports_list = report_model.get_pending()
    for report in reports_list:
        report['_id'] = str(report['_id'])
        # Enrich with contact details if they aren't already denormalized (for old reports)
        if not report.get('customer_name'):
            customer = user_model.find_by_id(report.get('reporter_id'))
            if customer:
                report['customer_name'] = customer.get('full_name')
                report['customer_mobile'] = customer.get('mobile')
        
        if not report.get('worker_name'):
            worker = worker_model.find_by_id(report.get('worker_id'))
            if worker:
                report['worker_name'] = worker.get('full_name', 'Deleted Worker')
                report['worker_mobile'] = worker.get('mobile', 'N/A')
                report['worker_email'] = worker.get('email', 'N/A')
            else:
                report['worker_name'] = 'Deleted Worker'
                report['worker_mobile'] = 'N/A'
                report['worker_email'] = 'N/A'

    # Wrap stats into a dictionary for the template
    stats = {
        'total_users': total_users,
        'total_workers': total_workers,
        'active_workers': active_workers,
        'banned_workers': banned_workers
    }

    return render_template('admin_dashboard.html', 
                          stats=stats,
                          reports=reports_list)


@app.route('/admin/manage_workers', methods=['GET', 'POST'])
@admin_required
def manage_workers():
    """Search and manage workers by ID or list all"""
    search_id = request.args.get('worker_id', '').strip()
    workers_list = []
    
    if search_id:
        worker = worker_model.find_by_id(search_id)
        if worker:
            workers_list = [worker]
        else:
            flash('Worker not found', 'error')
    else:
        workers_list = worker_model.get_all_workers()
        
    return render_template('admin_manage_workers.html', workers=workers_list)


@app.route('/admin/ban_worker/<worker_id>/<int:ban>', methods=['GET', 'POST'])
@admin_required
def ban_worker(worker_id, ban):
    """Ban or unban a worker with optional duration"""
    is_banned = True if ban == 1 else False
    duration_days = None
    
    if is_banned and request.method == 'POST':
        try:
            duration_days = int(request.form.get('duration_days', 0))
        except ValueError:
            duration_days = 0 # Permanent
    
    worker_model.update_ban_status(worker_id, is_banned, duration_days)
    
    # Log the action
    worker = worker_model.find_by_id(worker_id)
    action_text = "Banned" if is_banned else "Unbanned"
    duration_text = f" for {duration_days} days" if duration_days and duration_days > 0 else " permanently" if is_banned else ""
    audit_log.log('USER_STATUS', f"Worker {action_text}", session.get('email'), 
                  f"Worker: {worker.get('full_name')} ({worker_id}){duration_text}")
    
    status_text = 'banned' if is_banned else 'unbanned'
    flash(f'Worker {status_text} successfully', 'success')
    return redirect(request.referrer or url_for('manage_workers'))

@app.route('/admin/payments')
@admin_required
def admin_payments():
    """Manage worker withdrawal requests"""
    withdrawals = withdrawal_model.get_pending()
    return render_template('admin_payments.html', withdrawals=withdrawals)

@app.route('/admin/complete_payment/<withdrawal_id>', methods=['POST'])
@admin_required
def admin_complete_payment(withdrawal_id):
    """Mark a withdrawal request as completed"""
    w_req = withdrawal_model.find_by_id(withdrawal_id)
    if not w_req:
        flash('Withdrawal request not found', 'error')
        return redirect(url_for('admin_payments'))
    
    withdrawal_model.mark_completed(withdrawal_id)
    
    # Log the payment
    audit_log.log('PAYMENT', "Withdrawal Completed", session.get('email'), 
                  f"Worker: {w_req.get('worker_name')}, Amount: ₹{w_req.get('final_amount')}")
    
    flash(f"Payment for {w_req.get('worker_name')} marked as completed.", 'success')
    return redirect(url_for('admin_payments'))

@app.route('/admin/logs')
@admin_required
def admin_logs():
    """View system audit logs"""
    category = request.args.get('category')
    logs_list = audit_log.get_logs(category=category)
    return render_template('admin_logs.html', logs=logs_list, current_category=category)

@app.route('/admin/delete_worker/<worker_id>')
@admin_required
def delete_worker(worker_id):
    """Permanently delete a worker"""
    worker = worker_model.find_by_id(worker_id)
    if worker:
        worker_model.delete(worker_id)
        flash('Worker account has been permanently deleted.', 'success')
    else:
        flash('Worker not found', 'error')
    return redirect(url_for('manage_workers'))


@app.route('/admin/resolve_report/<report_id>')
@admin_required
def resolve_report(report_id):
    """Resolve a pending report"""
    report = db.reports.find_one({'_id': ObjectId(report_id)})
    report_model.resolve(report_id)
    
    # Log the action
    if report:
        audit_log.log('REPORT', "Report Resolved", session.get('email'), 
                      f"Report against Worker ID: {report.get('worker_id')}")
        
    flash('Report marked as resolved', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))


@app.route('/dashboard')
@login_required
def dashboard():
    """
    Role-based dashboard
    """
    # If admin is in session, redirect to admin dashboard
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))

    role = session.get('role')
    user_id = session.get('user_id')
    
    # Get user data
    user_data = auth.get_user_by_id_and_role(user_id, role)
    
    if not user_data:
        flash('User not found', 'error')
        return redirect(url_for('logout'))
    
    # Prepare role-specific data
    context = {
        'user_data': user_data,
        'role': role
    }
    
    if role == 'user':
        # User dashboard: Show recent workers
        context['recent_workers'] = worker_model.get_all_active()[:6]
        context['worker_types'] = Config.WORKER_TYPES
        # Show user appointments
        context['appointments'] = appointment_model.find_by_user(user_id)
    
    elif role == 'worker':
        # Worker dashboard: Show profile info & toggle
        context['is_active'] = user_data.get('is_active', True)
        
        # Calculate dynamic monthly balance (paid but not yet withdrawn)
        unpaid_bills = bill_model.get_unpaid_by_worker(user_id)
        user_data['income_balance'] = sum(bill.get('total', 0) for bill in unpaid_bills)
        
        # Recent feedback
        context['reviews'] = review_model.find_by_worker(user_id, limit=5)
        # Appointments
        context['appointments'] = appointment_model.find_by_worker(user_id)

    # Enrich appointments with secondary data
    if 'appointments' in context:
        for app_item in context['appointments']:
            if app_item.get('bill_id'):
                bill = bill_model.find_by_id(app_item['bill_id'])
                if bill:
                    app_item['bill_paid'] = bill.get('paid', False)
                    
            # If viewer is a worker, enrich the appointment with the customer's phone number for coordination
            if role == 'worker':
                appointment_user = user_model.find_by_id(app_item.get('user_id'))
                if appointment_user:
                    app_item['user_mobile'] = appointment_user.get('mobile', 'N/A')
                else:
                    app_item['user_mobile'] = 'N/A'

    return render_template('dashboard.html', **context)


@app.route('/worker/salary')
@login_required
@role_required(['worker'])
def worker_salary():
    """Worker views monthly income and withdrawals"""
    worker_id = session.get('user_id')
    
    # Get all bills for this worker
    all_bills = bill_model.find_by_worker(worker_id)
    
    # Calculate income balance (paid by user but not yet withdrawn)
    unpaid_bills = bill_model.get_unpaid_by_worker(worker_id)
    current_balance = sum(bill.get('total', 0) for bill in unpaid_bills)
    
    # Group income by month for history
    income_history = {} # {'Month Year': total}
    for bill in all_bills:
        if bill.get('paid'):
            month_key = bill['created_at'].strftime('%B %Y')
            income_history[month_key] = income_history.get(month_key, 0) + bill.get('total', 0)
    
    # Get withdrawal history
    withdrawals = withdrawal_model.get_by_worker(worker_id)
    
    # Check if we are on one of the configured withdrawal dates
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist)
    withdraw_dates = app.config.get('WITHDRAWAL_DATES', [28])
    can_withdraw = today.day in withdraw_dates and current_balance > 0
    
    return render_template('worker_salary.html', 
                          current_balance=current_balance,
                          income_history=income_history,
                          withdrawals=withdrawals,
                          can_withdraw=can_withdraw)

@app.route('/worker/request_withdrawal', methods=['GET', 'POST'])
@login_required
@role_required(['worker'])
def worker_request_withdrawal():
    """Worker submits withdrawal request"""
    worker_id = session.get('user_id')
    worker = worker_model.find_by_id(worker_id)
    
    unpaid_bills = bill_model.get_unpaid_by_worker(worker_id)
    current_balance = sum(bill.get('total', 0) for bill in unpaid_bills)
    
    if current_balance <= 0:
        flash('You have no balance to withdraw.', 'error')
        return redirect(url_for('worker_salary'))

    if request.method == 'POST':
        method = request.form.get('method') # bank or upi
        details = {}
        
        if method == 'bank':
            details = {
                'name': request.form.get('bank_name'),
                'account_no': request.form.get('account_no'),
                'ifsc': request.form.get('ifsc')
            }
        else:
            details = {
                'name': request.form.get('upi_name'),
                'upi_id': request.form.get('upi_id')
            }
            
        # Calculate fee based on config
        fee_percent = app.config.get('PLATFORM_FEE_PERCENTAGE', 10)
        fee_fraction = fee_percent / 100.0
        
        withdrawal_id = withdrawal_model.create(
            worker_id=worker_id,
            worker_name=worker.get('full_name'),
            amount=current_balance,
            method=method,
            details=details,
            fee_fraction=fee_fraction
        )
        
        # Mark bills as withdrawn (in-process)
        bill_ids = [str(b['_id']) for b in unpaid_bills]
        bill_model.mark_withdrawn(bill_ids)
        
        # Log the action
        audit_log.log('PAYMENT', "Withdrawal Requested", worker.get('email'), 
                      f"Amount: ₹{current_balance}, Method: {method.upper()}")
        
        flash('Withdrawal request submitted! Admin will process this soon.', 'success')
        return redirect(url_for('worker_salary'))

    # Get fee from config for display
    fee_percent = app.config.get('PLATFORM_FEE_PERCENTAGE', 10)
    fee_fraction = fee_percent / 100.0
    
    return render_template('worker_request_withdrawal.html', 
                          current_balance=current_balance,
                          platform_fee=current_balance * fee_fraction,
                          final_amount=current_balance * (1.0 - fee_fraction))


@app.route('/worker/view_withdrawal_bill/<withdrawal_id>')
@login_required
@role_required(['worker'])
def view_withdrawal_bill(withdrawal_id):
    """View a specific withdrawal statement/bill"""
    record = withdrawal_model.find_by_id(withdrawal_id)
    if not record:
        flash('Withdrawal record not found', 'error')
        return redirect(url_for('worker_salary'))
    
    # Security: Ensure worker owns this record
    if record.get('worker_id') != session.get('user_id'):
        flash('Unauthorized', 'error')
        return redirect(url_for('worker_salary'))
        
    return render_template('view_withdrawal_bill.html', record=record)


@app.route('/toggle_status')
@login_required
@role_required(['worker'])
def toggle_status():
    """Toggle worker active status"""
    worker_id = session.get('user_id')
    new_status = worker_model.toggle_status(worker_id)
    status_text = 'Active' if new_status else 'Inactive'
    flash(f'Status changed to {status_text}', 'success')
    return redirect(url_for('dashboard'))


@app.route('/workers')
@login_required
def workers():
    """
    Worker listing and search page
    """
    # Get search parameters
    worker_type = request.args.get('worker_type', 'all')
    pincode = request.args.get('pincode', '').strip()
    city = request.args.get('city', '').strip()
    
    # Search workers
    workers_list = worker_model.search(
        worker_type=worker_type if worker_type != 'all' else None,
        pincode=pincode if pincode else None,
        city=city if city else None
    )
    
    # Fetch all unique worker types actually in use to include custom ones in suggestions
    db_types = worker_model.collection.distinct('worker_type')
    
    # Filter out 'Other' and combine with predefined types, unique only
    worker_types = sorted(list(set(
        [t for t in Config.WORKER_TYPES if t != 'Other'] + 
        [t for t in db_types if t and t != 'Other']
    )))
    
    return render_template('workers.html', 
                          workers=workers_list,
                          worker_types=worker_types,
                          selected_type=worker_type,
                          selected_pincode=pincode,
                          selected_city=city)


@app.route('/worker/<worker_id>')
@login_required
def worker_profile(worker_id):
    """
    Individual worker profile page
    """
    worker = worker_model.find_by_id(worker_id)
    
    if not worker:
        flash('Worker not found', 'error')
        return redirect(url_for('workers'))
    
    # Get recent reviews
    reviews_list = review_model.find_by_worker(worker_id)
    
    return render_template('worker_profile.html', 
                          worker=worker, 
                          reviews=reviews_list,
                          role=session.get('role'))


@app.route('/make_appointment/<worker_id>', methods=['POST'])
@login_required
@role_required(['user'])
def make_appointment(worker_id):
    """User makes an appointment with a worker"""
    user_id = session.get('user_id')
    user = user_model.find_by_id(user_id)
    worker = worker_model.find_by_id(worker_id)
    
    if not user or not worker:
        flash('Error processing appointment', 'error')
        return redirect(url_for('workers'))
        
    date = request.form.get('date')
    time_slot = request.form.get('time_slot', '')
    details = request.form.get('details', '')
    
    if not date:
        flash('Please select a date', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))

    if not time_slot:
        flash('Please select a time slot', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))
        
    appointment_model.create(
        user_id=user_id,
        worker_id=worker_id,
        user_name=user.get('full_name'),
        worker_name=worker.get('full_name'),
        service_type=worker.get('worker_type'),
        date=date,
        time_slot=time_slot,
        address=user.get('address'),
        details=details
    )
    
    # Log the action
    audit_log.log('APPOINTMENT', "New Appointment Requested", user.get('email'), 
                  f"Customer booked Worker: {worker.get('full_name')} for {date}")
    
    flash('Appointment requested successfully!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/manage_appointment/<app_id>/<status>')
@login_required
@role_required(['worker'])
def manage_appointment(app_id, status):
    """Worker accepts or rejects appointment"""
    if status not in ['accepted', 'rejected', 'completed']:
        flash('Invalid status update', 'error')
        return redirect(url_for('dashboard'))

    appointment_model.update_status(app_id, status)
    
    # Log the action
    app_data = appointment_model.find_by_id(app_id)
    if app_data:
        audit_log.log('APPOINTMENT', f"Appointment {status.capitalize()}", session.get('email'), 
                      f"Appointment ID: {app_id}, Status set to: {status}")
        
        user = user_model.find_by_id(app_data.get('user_id'))
        worker = worker_model.find_by_id(app_data.get('worker_id'))
        if user and worker and status in ['accepted', 'rejected']:
            appointment_date = app_data.get('date', 'N/A')
            appointment_time = app_data.get('time_slot', 'N/A')
            if status == 'accepted':
                sms_message = (
                    f"Hi {user.get('full_name')}, your CrewHub appointment with {worker.get('full_name')} "
                    f"on {appointment_date} at {appointment_time} has been accepted.\n"
                    f"Check details: {Config.PLATFORM_URL}"
                )
            else:
                sms_message = (
                    f"Hi {user.get('full_name')}, your CrewHub appointment with {worker.get('full_name')} "
                    f"on {appointment_date} at {appointment_time} has been declined.\n"
                    f"Please visit {Config.PLATFORM_URL} to book another worker."
                )
            send_sms_message(user.get('mobile'), sms_message)

    # Redirect to bill generation when completing
    if status == 'completed':
        return redirect(url_for('generate_bill', app_id=app_id))

    flash(f'Appointment {status}', 'success')
    return redirect(url_for('dashboard'))


@app.route('/generate_bill/<app_id>', methods=['GET', 'POST'])
@login_required
@role_required(['worker'])
def generate_bill(app_id):
    """Worker generates bill after completing an appointment"""
    appointment = appointment_model.find_by_id(app_id)
    if not appointment:
        flash('Appointment not found', 'error')
        return redirect(url_for('dashboard'))

    # Ensure worker owns this appointment
    if appointment.get('worker_id') != session.get('user_id'):
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard'))

    # Check if bill already exists
    existing_bill = bill_model.find_by_appointment(app_id)
    if existing_bill:
        flash('Bill already generated for this appointment', 'warning')
        return redirect(url_for('view_bill', bill_id=str(existing_bill['_id'])))

    user = user_model.find_by_id(appointment.get('user_id'))
    worker = worker_model.find_by_id(appointment.get('worker_id'))

    if request.method == 'POST':
        descriptions = request.form.getlist('description')
        amounts = request.form.getlist('amount')

        # Build items list — first item is always visiting charges
        items = [{'description': 'Visiting Charges', 'amount': 200}]
        for desc, amt in zip(descriptions, amounts):
            desc = desc.strip()
            try:
                amt = float(amt)
            except (ValueError, TypeError):
                continue
            if desc and amt > 0:
                items.append({'description': desc, 'amount': amt})

        total = sum(item['amount'] for item in items)

        bill_id = bill_model.create(
            appointment_id=app_id,
            user_id=appointment.get('user_id'),
            worker_id=appointment.get('worker_id'),
            user_name=appointment.get('user_name', user.get('full_name', '')),
            user_mobile=user.get('mobile', ''),
            user_address=user.get('address', ''),
            worker_name=appointment.get('worker_name', worker.get('full_name', '')),
            worker_id_display=str(worker.get('_id', '')),
            service_type=appointment.get('service_type', ''),
            items=items,
            total=total
        )

        # Link bill to appointment
        appointment_model.set_bill_id(app_id, bill_id)

        flash('Bill generated and sent to customer!', 'success')
        return redirect(url_for('view_bill', bill_id=bill_id))

    return render_template('generate_bill.html',
                           appointment=appointment,
                           user=user,
                           worker=worker)


@app.route('/bill/<bill_id>')
@login_required
def view_bill(bill_id):
    """View a generated bill/invoice"""
    bill = bill_model.find_by_id(bill_id)
    if not bill:
        flash('Bill not found', 'error')
        return redirect(url_for('dashboard'))

    # Only the user, worker, or admin can view
    user_id = session.get('user_id')
    role = session.get('role')
    if (bill.get('user_id') != user_id and bill.get('worker_id') != user_id
            and not session.get('admin')):
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard'))

    return render_template('view_bill.html', bill=bill)


@app.route('/mark_paid/<bill_id>')
@login_required
@role_required(['worker'])
def mark_paid(bill_id):
    """Worker marks a bill as paid after receiving payment"""
    bill = bill_model.find_by_id(bill_id)
    if not bill:
        flash('Bill not found', 'error')
        return redirect(url_for('dashboard'))

    if bill.get('worker_id') != session.get('user_id'):
        flash('Unauthorized', 'error')
        return redirect(url_for('dashboard'))

    bill_model.mark_paid(bill_id)
    
    # Log the action
    audit_log.log('PAYMENT', "Bill Marked Paid", session.get('email'), 
                  f"Bill ID: {bill_id}, Amount: ₹{bill.get('total')}")
                  
    flash('Bill marked as paid!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/submit_review/<worker_id>', methods=['POST'])
@login_required
@role_required(['user'])
def submit_review(worker_id):
    """User submits a review for a worker"""
    user_id = session.get('user_id')
    user = user_model.find_by_id(user_id)
    
    rating = request.form.get('rating')
    comment = request.form.get('comment', '')
    
    if not rating:
        flash('Please provide a rating', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))
        
    review_model.create(
        worker_id=worker_id,
        user_id=user_id,
        user_name=user.get('full_name'),
        rating=rating,
        comment=comment
    )
    
    flash('Review submitted successfully!', 'success')
    return redirect(url_for('worker_profile', worker_id=worker_id))


@app.route('/report_worker/<worker_id>', methods=['POST'])
@login_required
def report_worker(worker_id):
    """Reporter (User) reports a worker"""
    reporter_id = session.get('user_id')
    reason = request.form.get('reason')
    
    if not reason:
        flash('Please provide a reason for reporting', 'error')
        return redirect(url_for('worker_profile', worker_id=worker_id))
    
    # Handle optional evidence upload
    evidence_url = None
    evidence_file = request.files.get('evidence')
    if evidence_file and evidence_file.filename != '':
        # Check file size (10MB limit)
        # seek(0, 2) moves to end, tell() gives position (size)
        evidence_file.seek(0, 2)
        file_size = evidence_file.tell()
        evidence_file.seek(0) # reset position for upload
        
        if file_size > 10 * 1024 * 1024:
            flash('File too large. Maximum allowed size is 10MB.', 'error')
            return redirect(url_for('worker_profile', worker_id=worker_id))

        try:
            upload_result = cloudinary.uploader.upload(
                evidence_file, 
                folder="crewhub/reports",
                resource_type="auto" # handles both images and videos
            )
            evidence_url = upload_result['secure_url']
        except Exception as e:
            flash(f'Evidence upload failed: {str(e)}', 'error')
    
    # Get details for denormalization
    user = user_model.find_by_id(reporter_id)
    worker = worker_model.find_by_id(worker_id)
    
    report_model.create(
        worker_id=worker_id, 
        reporter_id=reporter_id, 
        reason=reason,
        customer_name=user.get('full_name'),
        customer_mobile=user.get('mobile'),
        worker_name=worker.get('full_name'),
        worker_mobile=worker.get('mobile'),
        evidence_url=evidence_url
    )
    
    # Log the action
    audit_log.log('REPORT', "New Report Submitted", user.get('email'), 
                  f"Report against Worker: {worker.get('full_name')} ({worker_id})")
    
    flash('Worker reported successfully. Admin will review this.', 'warning')
    return redirect(url_for('worker_profile', worker_id=worker_id))

@app.route('/admin/worker_requests')
@admin_required
def admin_worker_requests():
    """View pending worker verifications"""
    pending_workers = worker_model.get_pending_workers()
    return render_template('admin_worker_requests.html', pending_workers=pending_workers)

@app.route('/admin/approve_worker/<worker_id>', methods=['POST'])
@admin_required
def approve_worker(worker_id):
    """Approve a pending worker verification"""
    worker = worker_model.find_by_id(worker_id)
    if not worker:
        flash('Worker not found', 'error')
        return redirect(url_for('admin_worker_requests'))
        
    worker_model.approve(worker_id)
    send_verification_email(worker.get('email'), worker.get('full_name'), 'approved')

    sms_message = (
        f"Congratulations {worker.get('full_name')}! Your CrewHub worker account is verified and approved.\n"
        f"Login: {Config.PLATFORM_URL}/login\n"
        f"You can now start receiving jobs on CrewHub."
    )
    send_sms_message(worker.get('mobile'), sms_message)
    
    flash(f"Worker {worker.get('full_name')} approved successfully.", 'success')
    return redirect(url_for('admin_worker_requests'))

@app.route('/admin/reject_worker/<worker_id>', methods=['POST'])
@admin_required
def reject_worker(worker_id):
    """Reject a pending worker verification"""
    worker = worker_model.find_by_id(worker_id)
    if not worker:
        flash('Worker not found', 'error')
        return redirect(url_for('admin_worker_requests'))
        
    remark = request.form.get('remark', 'No reason provided')
    worker_model.reject(worker_id, remark)
    send_verification_email(worker.get('email'), worker.get('full_name'), 'rejected', remark)

    sms_message = (
        f"Hello {worker.get('full_name')}, your CrewHub worker application was rejected.\n"
        f"Reason: {remark}\n"
        f"Visit {Config.PLATFORM_URL} for next steps."
    )
    send_sms_message(worker.get('mobile'), sms_message)
    
    flash(f"Worker {worker.get('full_name')} rejected.", 'warning')
    return redirect(url_for('admin_worker_requests'))

@app.route('/logout')
def logout():
    """
    Logout route - clears session
    Security: Proper session management
    """
    session.clear()
    flash('You have been logged out successfully', 'success')
    return redirect(url_for('index'))


# Error handlers
@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors silently for background assets"""
    # Don't flash for common background requests that fail
    if request.path.endswith('.ico') or request.path.endswith('.map') or request.path.endswith('.json'):
        return '', 404
    
    flash('Page not found', 'error')
    return redirect(url_for('index'))


@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors"""
    flash('An internal error occurred', 'error')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
