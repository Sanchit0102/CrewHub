"""
Models module for CrewHub
Handles database operations and business logic using MongoDB
MVC Pattern: This is the Model layer
"""

from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from bson.objectid import ObjectId
import random

class Database:
    """
    Database connection manager
    Scalability: Implements connection pooling, can be extended for replica sets
    """
    
    def __init__(self, uri, db_name):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self._initialize_collections()
    
    def _initialize_collections(self):
        """Create collections if they don't exist"""
        collections = self.db.list_collection_names()
        
        if 'users' not in collections:
            self.db.create_collection('users')
            self.db.users.create_index('email', unique=True)
            self.db.users.create_index('mobile')
        
        if 'workers' not in collections:
            self.db.create_collection('workers')
            self.db.workers.create_index('email', unique=True)
            self.db.workers.create_index('mobile')
            self.db.workers.create_index('pincode')
            self.db.workers.create_index('worker_type')
        
        if 'societies' not in collections:
            self.db.create_collection('societies')
            self.db.societies.create_index('email', unique=True)
            self.db.societies.create_index('pincode')

        if 'appointments' not in collections:
            self.db.create_collection('appointments')
            self.db.appointments.create_index('worker_id')
            self.db.appointments.create_index('user_id')

        if 'reviews' not in collections:
            self.db.create_collection('reviews')
            self.db.reviews.create_index('worker_id')

        if 'reports' not in collections:
            self.db.create_collection('reports')
            self.db.reports.create_index('worker_id')

        if 'bills' not in collections:
            self.db.create_collection('bills')
            self.db.bills.create_index('appointment_id')
            self.db.bills.create_index('worker_id')
            self.db.bills.create_index('user_id')
            self.db.bills.create_index('invoice_number', unique=True)


class User:
    """
    User model for regular platform users
    Business Logic: Users can search and contact workers
    """
    
    def __init__(self, db):
        self.collection = db.users
        self.db = db
    
    def create(self, full_name, mobile, email, address, pincode, password):
        """
        Create a new user account
        Returns: user_id if successful, None if email already exists
        """
        # Check if email already exists
        if self.collection.find_one({'email': email}):
            return None
        
        user_data = {
            'full_name': full_name,
            'mobile': mobile,
            'email': email,
            'address': address,
            'pincode': pincode,
            'password': generate_password_hash(password),
            'role': 'user',
            'is_banned': False,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        result = self.collection.insert_one(user_data)
        return str(result.inserted_id)
    
    def find_by_email(self, email):
        """Find user by email"""
        return self.collection.find_one({'email': email})
    
    def find_by_id(self, user_id):
        """Find user by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(user_id)})
        except:
            return None
    
    def verify_password(self, email, password):
        """Verify user password"""
        user = self.find_by_email(email)
        if user and check_password_hash(user['password'], password):
            return user
        return None

    def set_reset_otp(self, email, otp, expires_at):
        return self.collection.update_one(
            {'email': email},
            {'$set': {'reset_otp': otp, 'reset_otp_expires': expires_at, 'updated_at': datetime.utcnow()}}
        )

    def verify_reset_otp(self, email, otp):
        user = self.find_by_email(email)
        if not user:
            return False
        if user.get('reset_otp') == otp and user.get('reset_otp_expires') and datetime.utcnow() < user.get('reset_otp_expires'):
            return True
        return False

    def update_password_by_email(self, email, password):
        return self.collection.update_one(
            {'email': email},
            {'$set': {
                'password': generate_password_hash(password),
                'reset_otp': None,
                'reset_otp_expires': None,
                'updated_at': datetime.utcnow()
            }}
        )

    def update_profile(self, user_id, full_name, mobile, pincode, address):
        return self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {
                'full_name': full_name,
                'mobile': mobile,
                'pincode': pincode,
                'address': address,
                'updated_at': datetime.utcnow()
            }}
        )

    def delete(self, user_id):
        self.collection.delete_one({'_id': ObjectId(user_id)})

    def get_all_users(self):
        return list(self.collection.find({'role': 'user'}))


class Worker:
    """
    Worker model for service providers
    Business Logic: Workers can be discovered by users based on skills and location
    """
    
    def __init__(self, db):
        self.collection = db.workers
        self.db = db
    
    def create(self, full_name, mobile, email, address, pincode, worker_type, available_cities, password, aadhar_path=None, cert_path=None, profile_photo_path=None):
        """
        Create a new worker account
        Returns: worker_id if successful, None if email already exists
        """
        existing_worker = self.collection.find_one({'email': email})
        
        worker_data = {
            'full_name': full_name,
            'mobile': mobile,
            'email': email,
            'address': address,
            'pincode': pincode,
            'worker_type': worker_type,
            'available_cities': available_cities,
            'password': generate_password_hash(password),
            'role': 'worker',
            'status': 'pending', # reset to pending if re-registering
            'rejection_remark': '',
            'aadhar_file': aadhar_path,
            'certificate_file': cert_path,
            'profile_photo': profile_photo_path,
            'is_active': False,
            'is_banned': False,
            'ban_until': None, # new field for temporary bans
            'income_balance': 0.0, # new field for payout tracking
            'updated_at': datetime.utcnow()
        }

        if existing_worker:
            if existing_worker.get('status') == 'rejected':
                # Re-registering after rejection
                self.collection.update_one({'email': email}, {'$set': worker_data})
                return str(existing_worker['_id'])
            else:
                # Already exists and is not rejected
                return None
        
        # New Registration
        worker_data['rating'] = 0.0
        worker_data['total_reviews'] = 0
        worker_data['payment_method'] = None
        worker_data['payment_details'] = {}
        result = self.collection.insert_one(worker_data)
        return str(result.inserted_id)
    
    def find_by_email(self, email):
        """Find worker by email"""
        return self.collection.find_one({'email': email})
    
    def find_by_id(self, worker_id):
        """Find worker by ID"""
        try:
            return self.collection.find_one({'_id': ObjectId(worker_id)})
        except:
            return None
    
    def verify_password(self, email, password):
        """Verify worker password"""
        worker = self.find_by_email(email)
        if worker and check_password_hash(worker['password'], password):
            return worker
        return None

    def set_reset_otp(self, email, otp, expires_at):
        return self.collection.update_one(
            {'email': email},
            {'$set': {'reset_otp': otp, 'reset_otp_expires': expires_at, 'updated_at': datetime.utcnow()}}
        )

    def verify_reset_otp(self, email, otp):
        worker = self.find_by_email(email)
        if not worker:
            return False
        if worker.get('reset_otp') == otp and worker.get('reset_otp_expires') and datetime.utcnow() < worker.get('reset_otp_expires'):
            return True
        return False

    def update_password_by_email(self, email, password):
        return self.collection.update_one(
            {'email': email},
            {'$set': {
                'password': generate_password_hash(password),
                'reset_otp': None,
                'reset_otp_expires': None,
                'updated_at': datetime.utcnow()
            }}
        )

    def update_profile(self, worker_id, mobile, pincode, address, available_cities, payment_method=None, payment_details=None):
        update_data = {
            'mobile': mobile,
            'pincode': pincode,
            'address': address,
            'available_cities': available_cities,
            'updated_at': datetime.utcnow()
        }
        if payment_method:
            update_data['payment_method'] = payment_method
            update_data['payment_details'] = payment_details or {}

        return self.collection.update_one(
            {'_id': ObjectId(worker_id)},
            {'$set': update_data}
        )

    def delete(self, worker_id):
        """Delete a worker entirely"""
        self.collection.delete_one({'_id': ObjectId(worker_id)})
    
    def search(self, worker_type=None, pincode=None, city=None):
        """
        Search workers by type, pincode and/or city
        """
        query = {'is_active': True, 'is_banned': False}
        
        if worker_type and worker_type != 'all':
            query['worker_type'] = {'$regex': f'^{worker_type}$', '$options': 'i'}
        
        if pincode:
            query['pincode'] = pincode

        if city:
            # Case insensitive search in available_cities string
            query['available_cities'] = {'$regex': city, '$options': 'i'}
        
        workers = list(self.collection.find(query))
        return workers
    
    def get_all_active(self):
        """Get all active workers (verified and not banned)"""
        return list(self.collection.find({'is_active': True, 'is_banned': False, 'status': 'approved'}))
    
    def get_all_workers(self):
        return list(self.collection.find())

    def get_pending_workers(self):
        """Get all workers awaiting approval"""
        return list(self.collection.find({'status': 'pending'}).sort('created_at', -1))

    def approve(self, worker_id):
        """Approve a worker"""
        self.collection.update_one(
            {'_id': ObjectId(worker_id)},
            {'$set': {'status': 'approved', 'is_active': True, 'updated_at': datetime.utcnow()}}
        )

    def reject(self, worker_id, remark):
        """Reject a worker with remark"""
        self.collection.update_one(
            {'_id': ObjectId(worker_id)},
            {'$set': {'status': 'rejected', 'rejection_remark': remark, 'is_active': False, 'updated_at': datetime.utcnow()}}
        )

    def toggle_status(self, worker_id):
        worker = self.find_by_id(worker_id)
        if worker:
            new_status = not worker.get('is_active', True)
            self.collection.update_one(
                {'_id': ObjectId(worker_id)},
                {'$set': {'is_active': new_status, 'updated_at': datetime.utcnow()}}
            )
            return new_status
        return None

    def update_ban_status(self, worker_id, is_banned, duration_days=None):
        update_data = {
            'is_banned': is_banned,
            'updated_at': datetime.utcnow()
        }
        
        if is_banned and duration_days:
            from datetime import timedelta
            update_data['ban_until'] = datetime.utcnow() + timedelta(days=duration_days)
        else:
            update_data['ban_until'] = None

        self.collection.update_one(
            {'_id': ObjectId(worker_id)},
            {'$set': update_data}
        )

    def delete(self, worker_id):
        """Delete a worker entirely"""
        self.collection.delete_one({'_id': ObjectId(worker_id)})

    def update_rating(self, worker_id, new_rating):
        worker = self.find_by_id(worker_id)
        if worker:
            current_total = worker.get('total_reviews', 0)
            current_rating = worker.get('rating', 0.0)
            
            new_total = current_total + 1
            avg_rating = ((current_rating * current_total) + new_rating) / new_total
            
            self.collection.update_one(
                {'_id': ObjectId(worker_id)},
                {'$set': {
                    'rating': round(avg_rating, 1),
                    'total_reviews': new_total,
                    'updated_at': datetime.utcnow()
                }}
            )

    def count_by_type(self):
        """Get count of workers by type - useful for analytics"""
        pipeline = [
            {'$match': {'is_active': True, 'is_banned': False}},
            {'$group': {'_id': '$worker_type', 'count': {'$sum': 1}}}
        ]
        return list(self.collection.aggregate(pipeline))



class Appointment:
    def __init__(self, db):
        self.collection = db.appointments
        self.db = db

    def create(self, user_id, worker_id, user_name, worker_name, service_type, date, time_slot, address, details):
        app_data = {
            'user_id': user_id,
            'worker_id': worker_id,
            'user_name': user_name,
            'worker_name': worker_name,
            'service_type': service_type,
            'date': date,
            'time_slot': time_slot,
            'address': address,
            'details': details,
            'status': 'pending',  # pending, accepted, rejected, completed
            'bill_id': None,
            'created_at': datetime.utcnow()
        }
        result = self.collection.insert_one(app_data)
        return str(result.inserted_id)

    def find_by_id(self, app_id):
        try:
            return self.collection.find_one({'_id': ObjectId(app_id)})
        except:
            return None

    def find_by_worker(self, worker_id):
        return list(self.collection.find({'worker_id': worker_id}).sort('created_at', -1))

    def find_by_user(self, user_id):
        return list(self.collection.find({'user_id': user_id}).sort('created_at', -1))

    def update_status(self, app_id, status):
        self.collection.update_one(
            {'_id': ObjectId(app_id)},
            {'$set': {'status': status, 'updated_at': datetime.utcnow()}}
        )

    def set_bill_id(self, app_id, bill_id):
        self.collection.update_one(
            {'_id': ObjectId(app_id)},
            {'$set': {'bill_id': bill_id}}
        )


class Review:
    def __init__(self, db):
        self.collection = db.reviews
        self.db = db

    def create(self, worker_id, user_id, user_name, rating, comment):
        review_data = {
            'worker_id': worker_id,
            'user_id': user_id,
            'user_name': user_name,
            'rating': float(rating),
            'comment': comment,
            'created_at': datetime.utcnow()
        }
        self.collection.insert_one(review_data)
        # Update worker rating
        Worker(self.db).update_rating(worker_id, float(rating))

    def find_by_worker(self, worker_id, limit=5):
        return list(self.collection.find({'worker_id': worker_id}).sort('created_at', -1).limit(limit))


class Report:
    def __init__(self, db):
        self.collection = db.reports
        self.db = db

    def create(self, worker_id, reporter_id, reason, customer_name=None, customer_mobile=None, worker_name=None, worker_mobile=None, evidence_url=None):
        report_data = {
            'worker_id': worker_id,
            'reporter_id': reporter_id,
            'reason': reason,
            'customer_name': customer_name,
            'customer_mobile': customer_mobile,
            'worker_name': worker_name,
            'worker_mobile': worker_mobile,
            'evidence_url': evidence_url,
            'status': 'pending', # pending, resolved
            'created_at': datetime.utcnow()
        }
        self.collection.insert_one(report_data)

    def get_pending(self):
        return list(self.collection.find({'status': 'pending'}).sort('created_at', -1))

    def resolve(self, report_id):
        self.collection.update_one(
            {'_id': ObjectId(report_id)},
            {'$set': {'status': 'resolved', 'resolved_at': datetime.utcnow()}}
        )


class Bill:
    """Bill / Invoice model for completed appointments"""

    def __init__(self, db):
        self.collection = db.bills
        self.db = db

    def generate_invoice_number(self):
        """Generate a unique invoice number between 1 and 10000"""
        used = set(doc['invoice_number'] for doc in self.collection.find({}, {'invoice_number': 1}))
        available = [n for n in range(1, 10001) if n not in used]
        if not available:
            # Fallback: extend range
            return random.randint(10001, 99999)
        return random.choice(available)

    def create(self, appointment_id, user_id, worker_id, user_name, user_mobile,
               user_address, worker_name, worker_id_display, service_type, items, total):
        invoice_number = self.generate_invoice_number()
        bill_data = {
            'appointment_id': appointment_id,
            'user_id': user_id,
            'worker_id': worker_id,
            'invoice_number': invoice_number,
            'user_name': user_name,
            'user_mobile': user_mobile,
            'user_address': user_address,
            'worker_name': worker_name,
            'worker_id_display': worker_id_display,
            'service_type': service_type,
            'items': items,       # list of {description, amount}
            'total': total,
            'paid': False,
            'created_at': datetime.utcnow()
        }
        result = self.collection.insert_one(bill_data)
        return str(result.inserted_id)

    def mark_paid(self, bill_id, payment_details=None):
        update_fields = {'paid': True, 'paid_at': datetime.utcnow()}
        if payment_details:
            update_fields.update(payment_details)

        self.collection.update_one(
            {'_id': ObjectId(bill_id)},
            {'$set': update_fields}
        )

    def find_by_id(self, bill_id):
        try:
            return self.collection.find_one({'_id': ObjectId(bill_id)})
        except:
            return None

    def find_by_appointment(self, appointment_id):
        return self.collection.find_one({'appointment_id': appointment_id})

    def find_by_worker(self, worker_id):
        return list(self.collection.find({'worker_id': worker_id}).sort('created_at', -1))

    def find_by_user(self, user_id):
        return list(self.collection.find({'user_id': user_id}).sort('created_at', -1))

    def get_unpaid_by_worker(self, worker_id):
        """Get all bills for a worker that are paid by customer but not yet withdrawn by worker"""
        return list(self.collection.find({
            'worker_id': worker_id, 
            'paid': True,
            'withdrawn': {'$ne': True}
        }).sort('created_at', -1))

    def mark_withdrawn(self, bill_ids):
        """Mark a list of bills as withdrawn"""
        # Clean and validate IDs
        valid_ids = []
        for bid in bill_ids:
            try:
                valid_ids.append(ObjectId(bid))
            except:
                continue
                
        if not valid_ids:
            return
            
        self.collection.update_many(
            {'_id': {'$in': valid_ids}},
            {'$set': {'withdrawn': True, 'withdrawn_at': datetime.utcnow()}}
        )


class Withdrawal:
    """Model for worker payout requests"""
    def __init__(self, db):
        self.collection = db.withdrawals
        self.db = db

    def create(self, worker_id, worker_name, amount, method, details, fee_fraction=0.10):
        platform_fee = amount * fee_fraction
        final_amount = amount - platform_fee
        
        withdrawal_data = {
            'worker_id': worker_id,
            'worker_name': worker_name,
            'requested_amount': amount,
            'platform_fee': platform_fee,
            'final_amount': final_amount,
            'method': method, # bank, upi
            'details': details, # {account_no, ifsc, name} or {upi_id, name}
            'status': 'pending', # pending, completed
            'created_at': datetime.utcnow()
        }
        result = self.collection.insert_one(withdrawal_data)
        return str(result.inserted_id)

    def get_pending(self):
        return list(self.collection.find({'status': 'pending'}).sort('created_at', -1))

    def get_by_worker(self, worker_id):
        return list(self.collection.find({'worker_id': worker_id}).sort('created_at', -1))

    def mark_completed(self, withdrawal_id):
        self.collection.update_one(
            {'_id': ObjectId(withdrawal_id)},
            {'$set': {'status': 'completed', 'completed_at': datetime.utcnow()}}
        )

    def find_by_id(self, withdrawal_id):
        try:
            return self.collection.find_one({'_id': ObjectId(withdrawal_id)})
        except:
            return None


class AuditLog:
    """Model for system activity logging"""
    def __init__(self, db):
        self.collection = db.audit_logs
        self.db = db

    def log(self, category, action, user_email, details):
        """
        Log an important system event
        Categories: REPORT, USER_STATUS, PAYMENT, APPOINTMENT
        """
        log_data = {
            'category': category,
            'action': action,
            'performed_by': user_email,
            'details': details,
            'created_at': datetime.utcnow()
        }
        self.collection.insert_one(log_data)

    def get_logs(self, category=None, limit=100):
        query = {}
        if category:
            query['category'] = category
        return list(self.collection.find(query).sort('created_at', -1).limit(limit))


class Authentication:
    """
    Unified authentication handler
    Business Logic: Single login portal for all user types
    """

    def __init__(self, db):
        self.user_model = User(db)
        self.worker_model = Worker(db)

    def authenticate(self, email, password):
        """
        Authenticate user across roles (user, worker)
        Returns: (user_data, role) if successful, (None, None) if failed
        """
        user = self.user_model.verify_password(email, password)
        if user:
            return user, 'user'

        worker = self.worker_model.verify_password(email, password)
        if worker:
            return worker, 'worker'

        return None, None

    def get_user_by_id_and_role(self, user_id, role):
        """Get user data by ID and role"""
        if role == 'user':
            return self.user_model.find_by_id(user_id)
        elif role == 'worker':
            return self.worker_model.find_by_id(user_id)
        return None
